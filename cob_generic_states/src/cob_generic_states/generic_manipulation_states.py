#!/usr/bin/python
#################################################################
##\file
#
# \note
#   Copyright (c) 2010 \n
#   Fraunhofer Institute for Manufacturing Engineering
#   and Automation (IPA) \n\n
#
#################################################################
#
# \note
#   Project name: care-o-bot
# \note
#   ROS stack name: cob_scenarios
# \note
#   ROS package name: cob_generic_states
#
# \author
#   Florian Weisshardt, email:florian.weisshardt@ipa.fhg.de
#
# \date Date of creation: Aug 2011
#
# \brief
#   Implements generic states which can be used in multiple scenarios.
#
#################################################################
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#     - Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer. \n
#     - Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution. \n
#     - Neither the name of the Fraunhofer Institute for Manufacturing
#       Engineering and Automation (IPA) nor the names of its
#       contributors may be used to endorse or promote products derived from
#       this software without specific prior written permission. \n
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License LGPL as 
# published by the Free Software Foundation, either version 3 of the 
# License, or (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License LGPL for more details.
# 
# You should have received a copy of the GNU Lesser General Public 
# License LGPL along with this program. 
# If not, see <http://www.gnu.org/licenses/>.
#
#################################################################

import rospy
import sys
import copy

import smach
import smach_ros

from simple_script_server import *
sss = simple_script_server()

import tf
from std_srvs.srv import Trigger
from moveit_msgs.srv import *
from sensor_msgs.msg import *


## Select grasp state
#
# This state select a grasping strategy. A high object will be grasped from the side, a low one from top.
class select_grasp(smach.State):

	def __init__(self):
		smach.State.__init__(
			self,
			outcomes=['top', 'side', 'failed'],
			input_keys=['object'])
		
		self.height_switch = 0.5 # Switch to select top or side grasp using the height of the object over the ground in [m].
		
		self.listener = tf.TransformListener()

	def execute(self, userdata):
		try:
			# transform object_pose into base_link
			object_pose_in = userdata.object.pose
			print object_pose_in
			object_pose_in.header.stamp = self.listener.getLatestCommonTime("/base_link",object_pose_in.header.frame_id)
			object_pose_bl = self.listener.transformPose("/base_link", object_pose_in)
		except rospy.ROSException, e:
			print "Transformation not possible: %s"%e
			return 'failed'
		
		if object_pose_bl.pose.position.z >= self.height_switch: #TODO how to select grasps for objects within a cabinet or shelf?
			return 'side'
		else: 
			return 'top'


## Grasp side state
#
# This state will grasp an object with a side grasp
class grasp_side(smach.State):

	def __init__(self, max_retries = 1):
		smach.State.__init__(
			self,
			outcomes=['grasped','not_grasped', 'failed'],
			input_keys=['object'])
		
		self.max_retries = max_retries
		self.retries = 0
		self.iks = rospy.ServiceProxy('/compute_ik', GetPositionIK)
		self.listener = tf.TransformListener()

	def callIKSolver(self, current_pose, goal_pose):
		req = GetPositionIKRequest()
		req.ik_request.ik_link_name = "sdh_grasp_link"
		#req.ik_request.ik_seed_state.joint_state.position = current_pose
		req.ik_request.pose_stamped = goal_pose
		resp = self.iks(req)
		result = []
		for o in resp.solution.joint_state.position:
			result.append(o)
		return (result, resp.error_code)

	def execute(self, userdata):
		# check if maximum retries reached
		if self.retries > self.max_retries:
			self.retries = 0
			handle_torso = sss.move("torso","home",False)
			handle_torso.wait()
			handle_arm = sss.move("arm","look_at_table-to-folded",False)
			return 'not_grasped'

		# transform object_pose into base_link
		object_pose_in = userdata.object.pose
		object_pose_in.header.stamp = self.listener.getLatestCommonTime("/base_link",object_pose_in.header.frame_id)
		object_pose_bl = self.listener.transformPose("/base_link", object_pose_in)
	
		[new_x, new_y, new_z, new_w] = tf.transformations.quaternion_from_euler(-1.5708, 0, 2.481) # rpy 
		object_pose_bl.pose.orientation.x = new_x
		object_pose_bl.pose.orientation.y = new_y
		object_pose_bl.pose.orientation.z = new_z
		object_pose_bl.pose.orientation.w = new_w

		# FIXME: this is calibration between camera and hand and should be removed from scripting level
		#object_pose_bl.pose.position.x = object_pose_bl.pose.position.x #- 0.06 #- 0.08
		#object_pose_bl.pose.position.y = object_pose_bl.pose.position.y #- 0.05
		object_pose_bl.pose.position.z = object_pose_bl.pose.position.z + 0.1
		
		# calculate pre and post grasp positions
		pre_grasp_bl = PoseStamped()
		post_grasp_bl = PoseStamped()
		pre_grasp_bl = copy.deepcopy(object_pose_bl)
		post_grasp_bl = copy.deepcopy(object_pose_bl)

		pre_grasp_bl.pose.position.x = pre_grasp_bl.pose.position.x + 0.0 # x offset for pre grasp position
		pre_grasp_bl.pose.position.y = pre_grasp_bl.pose.position.y + 0.10 # y offset for pre grasp position
		pre_grasp_bl.pose.position.z = pre_grasp_bl.pose.position.z + 0.2 # z offset for pre grasp position
		post_grasp_bl.pose.position.x = post_grasp_bl.pose.position.x + 0.05 # x offset for post grasp position
		post_grasp_bl.pose.position.z = post_grasp_bl.pose.position.z + 0.17 # z offset for post grasp position
		
		# calculate ik solutions for pre grasp configuration
		arm_pre_grasp = rospy.get_param("/script_server/arm/pregrasp")
		(pre_grasp_conf, error_code) = self.callIKSolver(arm_pre_grasp[0], pre_grasp_bl)		
		if(error_code.val != error_code.SUCCESS):
			rospy.logerr("Ik pre_grasp Failed")
			self.retries += 1
			return 'not_grasped'
		
		# calculate ik solutions for grasp configuration
		(grasp_conf, error_code) = self.callIKSolver(pre_grasp_conf, object_pose_bl)
		if(error_code.val != error_code.SUCCESS):
			rospy.logerr("Ik grasp Failed")
			self.retries += 1
			return 'not_grasped'
		
		# calculate ik solutions for pre grasp configuration
		(post_grasp_conf, error_code) = self.callIKSolver(grasp_conf, post_grasp_bl)
		if(error_code.val != error_code.SUCCESS):
			rospy.logerr("Ik post_grasp Failed")
			self.retries += 1
			return 'not_grasped'

		# execute grasp
		sss.say("sound", ["I am grasping the " + userdata.object.label + " now."],False)
		sss.move("torso","front")
		handle_arm = sss.move("arm", [pre_grasp_conf , grasp_conf],False)
		sss.move("sdh", "cylopen")
		handle_arm.wait()
		sss.move("sdh", "cylclosed")
	
		# move object to hold position
		sss.move("head","front",False)
		sss.move("arm", [post_grasp_conf, "hold"])
		
		self.retries = 0
		return 'grasped'


## Grasp side state with planned arm movements
#
# This state will grasp an object with a side grasp
class grasp_side_planned(smach.State):

	def __init__(self, max_retries = 1):
		smach.State.__init__(
			self,
			outcomes=['grasped','not_grasped', 'failed'],
			input_keys=['object'])
		
		self.max_retries = max_retries
		self.retries = 0
		self.transformer = rospy.ServiceProxy('/cob_pose_transform/get_pose_stamped_transformed', GetPoseStampedTransformed)
		self.grasped = rospy.ServiceProxy('/sdh_controller/is_cylindric_grasped', Trigger)

	def execute(self, userdata):
		# check if maximum retries reached
		if self.retries > self.max_retries:
			sss.set_light("light", 'yellow')
			self.retries = 0
			handle_torso = sss.move("torso","home",False)
			handle_torso.wait()
			handle_arm = sss.move("arm","look_at_table-to-folded",False)
			return 'not_grasped'

		# transform object_pose to middle
		object_pose_in = userdata.object.pose
		print object_pose_in
		#object_pose_in.header.stamp = self.listener.getLatestCommonTime("/base_link",object_pose_in.header.frame_id)
		#object_pose_in.pose.position.x += userdata.object.bounding_box_lwh.x/2.0
		#object_pose_in.pose.position.y += userdata.object.bounding_box_lwh.y/2.0
		#object_pose_in.pose.position.z += userdata.object.bounding_box_lwh.z/2.0
		
		
		[new_x, new_y, new_z, new_w] = tf.transformations.quaternion_from_euler(-1.552, -0.042, 2.481) # rpy 
		req = GetPoseStampedTransformedRequest()
		req.tip_name = "arm_7_link"
		req.root_name = "arm_base_link"
		req.target = object_pose_in
		req.orientation_override.x = new_x
		req.orientation_override.y = new_y
		req.orientation_override.z = new_z
		req.orientation_override.w = new_w

		req.origin.header.frame_id='sdh_grasp_link'
		req.origin.header.stamp=req.target.header.stamp
		
		res = self.transformer(req)
		if not res.success:
			print "Service call GetPoseStampedTransformed failed", sys.exc_info()
			sss.set_light("light", 'red')
			self.retries = 0
			return 'failed'
		
		object_pose_bl = res.result
		object_pose_bl.pose.position.z += userdata.object.bounding_box_lwh.z/2.0

		#[new_x, new_y, new_z, new_w] = tf.transformations.quaternion_from_euler(-0.290, -1.413, -1.145) # rpy 
		#object_pose_bl.pose.orientation.x = new_x
		#object_pose_bl.pose.orientation.y = new_y
		#object_pose_bl.pose.orientation.z = new_z
		#object_pose_bl.pose.orientation.w = new_w

		# calculate pre and post grasp positions
		pre_grasp_bl = PoseStamped()
		post_grasp_bl = PoseStamped()
		pre_grasp_bl = copy.deepcopy(object_pose_bl)
		post_grasp_bl = copy.deepcopy(object_pose_bl)

		#TODO: check offsets
		pre_grasp_bl.pose.position.x = pre_grasp_bl.pose.position.x + 0.0 # x offset for pre grasp position
		pre_grasp_bl.pose.position.y = pre_grasp_bl.pose.position.y + 0.10 # y offset for pre grasp position
		pre_grasp_bl.pose.position.z = pre_grasp_bl.pose.position.z + 0.2 # z offset for pre grasp position
		post_grasp_bl.pose.position.x = post_grasp_bl.pose.position.x + 0.05 # x offset for post grasp position
		post_grasp_bl.pose.position.z = post_grasp_bl.pose.position.z + 0.17 # z offset for post grasp position

		sss.set_light("light", 'blue')
	
		# calculate ik solutions for pre grasp configuration
		seed_js = JointState()
		seed_js.name = rospy.get_param("/arm_controller/joint_names")
		seed_js.position = rospy.get_param("/script_server/arm/pregrasp")[0]
		pre_grasp_js, error_code = sss.calculate_ik(pre_grasp_bl,seed_js)
		if(error_code.val != error_code.SUCCESS):
			if error_code.val != error_code.NO_IK_SOLUTION:
				sss.set_light("light", 'red')
			rospy.logerr("Ik pre_grasp Failed")
			self.retries += 1
			return 'not_grasped'
		
		# calculate ik solutions for grasp configuration
		grasp_js, error_code = sss.calculate_ik(object_pose_bl, pre_grasp_js)
		if(error_code.val != error_code.SUCCESS):
			if error_code.val != error_code.NO_IK_SOLUTION:
				sss.set_light("light", 'red')
			rospy.logerr("Ik grasp Failed")
			self.retries += 1
			return 'not_grasped'
		
		# calculate ik solutions for pre grasp configuration
		post_grasp_js, error_code = sss.calculate_ik(post_grasp_bl, grasp_js)
		if(error_code.val != error_code.SUCCESS):
			if error_code.val != error_code.NO_IK_SOLUTION:
				sss.set_light("light", 'red')
			rospy.logerr("Ik post_grasp Failed")
			self.retries += 1
			return 'not_grasped'

		# execute grasp
		sss.set_light("light", 'yellow')
		sss.say("sound", ["I am grasping the " + userdata.object.label + " now."],False)
		#handle_arm = sss.move("arm", [pre_grasp_conf , grasp_conf],False)
		handle_arm = sss.move_planned("arm", [list(pre_grasp_js.position)],False)
		sss.move("sdh", "cylopen",False)
		handle_arm.wait()
		handle_arm = sss.move("arm", [list(grasp_js.position)]) # TODO: use interpolated IK
		sss.move("sdh", "cylclosed")
	
		# move object to frontside and put object on tray
		sss.move("head","front",False)
		sss.move("torso","front")
		handle_arm = sss.move("arm", [list(post_grasp_js.position)]) # TODO: use interpolated IK
		handle_arm = sss.move("arm", 'hold')
		
		self.retries = 0
		if self.grasped().success.data:
			return 'grasped'
		else:
			sss.say("sound", ["I could not grasp " + userdata.object.label],False)
			return 'not_grasped'
		
## Grasp top state
#
# This state will grasp an object with a top grasp
class grasp_top(smach.State):

	def __init__(self, max_retries = 1):
		smach.State.__init__(
			self,
			outcomes=['succeeded', 'no_ik_solution', 'no_more_retries', 'failed'],
			input_keys=['object'])
		
		self.max_retries = max_retries
		self.retries = 0
		self.iks = rospy.ServiceProxy('/compute_ik', GetPositionIK)
		self.listener = tf.TransformListener()

	def callIKSolver(self, current_pose, goal_pose):
		req = GetPositionIKRequest()
		req.ik_request.ik_link_name = "sdh_grasp_link"
		#req.ik_request.ik_seed_state.joint_state.position = current_pose
		req.ik_request.pose_stamped = goal_pose
		resp = self.iks(req)
		result = []
		for o in resp.solution.joint_state.position:
			result.append(o)
		return (result, resp.error_code)

	def execute(self, userdata):
		# check if maximum retries reached
		if self.retries > self.max_retries:
			self.retries = 0
			handle_torso = sss.move("torso","home",False)
			handle_torso.wait()
			handle_arm = sss.move("arm","look_at_table-to-folded",False)
			return 'no_more_retries'

		# transform object_pose into base_link
		object_pose_in = userdata.object.pose
		object_pose_in.header.stamp = self.listener.getLatestCommonTime("/base_link",object_pose_in.header.frame_id)
		object_pose_bl = self.listener.transformPose("/base_link", object_pose_in)
	
		# use a predefined (fixed) orientation for object_pose_bl
		[new_x, new_y, new_z, new_w] = tf.transformations.quaternion_from_euler(3.121, 0.077, -2.662) # rpy 
		object_pose_bl.pose.orientation.x = new_x
		object_pose_bl.pose.orientation.y = new_y
		object_pose_bl.pose.orientation.z = new_z
		object_pose_bl.pose.orientation.w = new_w

		# FIXME: this is calibration between camera and hand and should be removed from scripting level
		object_pose_bl.pose.position.x = object_pose_bl.pose.position.x #-0.04 #- 0.08
		object_pose_bl.pose.position.y = object_pose_bl.pose.position.y# + 0.02
		object_pose_bl.pose.position.z = object_pose_bl.pose.position.z #+ 0.07

		# calculate pre and post grasp positions
		pre_grasp_bl = PoseStamped()
		post_grasp_bl = PoseStamped()
		pre_grasp_bl = copy.deepcopy(object_pose_bl)
		post_grasp_bl = copy.deepcopy(object_pose_bl)
	
		pre_grasp_bl.pose.position.z = pre_grasp_bl.pose.position.z + 0.18 # z offset for pre grasp position
		post_grasp_bl.pose.position.x = post_grasp_bl.pose.position.x + 0.05 # x offset for post grasp position
		post_grasp_bl.pose.position.z = post_grasp_bl.pose.position.z + 0.15 # z offset for post grasp position
		
		# calculate ik solutions for pre grasp configuration
		arm_pre_grasp = rospy.get_param("/script_server/arm/pregrasp_top")
		(pre_grasp_conf, error_code) = self.callIKSolver(arm_pre_grasp[0], pre_grasp_bl)		
		if(error_code.val != error_code.SUCCESS):
			rospy.logerr("Ik pre_grasp Failed")
			self.retries += 1
			return 'no_ik_solution'
		
		# calculate ik solutions for grasp configuration
		(grasp_conf, error_code) = self.callIKSolver(pre_grasp_conf, object_pose_bl)
		if(error_code.val != error_code.SUCCESS):
			rospy.logerr("Ik grasp Failed")
			self.retries += 1
			return 'no_ik_solution'
		
		# calculate ik solutions for pre grasp configuration
		(post_grasp_conf, error_code) = self.callIKSolver(grasp_conf, post_grasp_bl)
		if(error_code.val != error_code.SUCCESS):
			rospy.logerr("Ik post_grasp Failed")
			self.retries += 1
			return 'no_ik_solution'	

		# execute grasp
		sss.say("sound", ["I am grasping the " + userdata.object.label + " now."],False)
		sss.move("torso","home")
		handle_arm = sss.move("arm", [pre_grasp_conf , grasp_conf],False)
		sss.move("sdh", "spheropen")
		handle_arm.wait()
		sss.move("sdh", "spherclosed")
	
		# move object to frontside and put object on tray
		sss.move("head","front",False)
		sss.move("arm", [post_grasp_conf, "hold"])
		
		self.retries = 0
		return 'succeeded'



## Put object on tray side state
#
# This state puts a side grasped object on the tray
class put_object_on_tray_side(smach.State):

	def __init__(self):
		smach.State.__init__(
			self,
			outcomes=['succeeded', 'failed'])

	def execute(self, userdata):
		#TODO select position on tray depending on how many objects are on the tray already
		
		# move object to frontside
		handle_arm = sss.move("arm","grasp-to-tray",False)
		sss.sleep(2)
		sss.move("tray","up")
		handle_arm.wait()
		
		# release object
		sss.move("sdh","cylopen")
		
		# move arm to backside again
		handle_arm = sss.move("arm","tray-to-folded",False)
		sss.sleep(3)
		sss.move("sdh","home")
		handle_arm.wait()
		return 'succeeded'


## Put object on tray top state
#
# This state puts a top grasped object on the tray
class put_object_on_tray_top(smach.State):

	def __init__(self):
		smach.State.__init__(
			self,
			outcomes=['succeeded', 'failed'])

	def execute(self, userdata):
		#TODO select position on tray depending on how many objects are on the tray already
		
		# move object to frontside
		handle_arm = sss.move("arm","grasp-to-tray_top",False)
		sss.sleep(2)
		sss.move("tray","up")
		handle_arm.wait()
		
		# release object
		sss.move("sdh","spheropen")
		
		# move arm to backside again
		handle_arm = sss.move("arm","tray_top-to-folded",False)
		sss.sleep(3)
		sss.move("sdh","home",False)
		handle_arm.wait()
		return 'succeeded'


## Put object on table state for side grasps
#
# This state puts a side grasped object on a table, assuming that the robot is already in front of the table
class put_object_on_table(smach.State):

	def __init__(self):
		smach.State.__init__(
			self,
			outcomes=['succeeded', 'failed'],
			input_keys=['object_target_pose'])

	def execute(self, userdata):
		# TODO: for placing the object the wrench information from the arm could be used to determine the placing height exactly
		# TODO: tke into account the current grasping configuration and use this for releasing the object on the table. FIXME: At the moment only a fixed position is used

		# move object to release position
		sss.move("arm","pregrasp")

		# release object
		sss.move("sdh","cylopen")

		# move arm to backside again
		handle_arm = sss.move("arm",["hold","folded"],False)
		sss.sleep(3)
		sss.move("sdh","home",False)
		handle_arm.wait()
		return 'succeeded'
