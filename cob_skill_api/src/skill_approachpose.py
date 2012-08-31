#!/usr/bin/env python

#################################################################
##\file
#
# \note
# Copyright (c) 2012 \n
# Fraunhofer Institute for Manufacturing Engineering
# and Automation (IPA) \n\n
#
#################################################################
#
# \note
# Project name: Care-O-bot Research
# \note
# ROS package name: cob_skill_api
#
# \author
# Author: Thiago de Freitas Oliveira Araujo, 
# email:thiago.de.freitas.oliveira.araujo@ipa.fhg.de
# \author
# Supervised by: Florian Weisshardt, email:florian.weisshardt@ipa.fhg.de
#
# \date Date of creation: August 2012
#
# \brief
# Implementation of the Skill ApproachPose
#
#################################################################
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# - Redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer. \n
# - Redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution. \n
# - Neither the name of the Fraunhofer Institute for Manufacturing
# Engineering and Automation (IPA) nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission. \n
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
# If not, see < http://www.gnu.org/licenses/>.
#
#################################################################

#!/usr/bin/python

import abc
from abc_skill import SkillsBase
import yaml

import roslib
roslib.load_manifest('cob_skill_api')
import rospy
import smach
import smach_ros
from actionlib import *
from actionlib.msg import *
import random

import pre_check
import post_check
import skill_state_approachpose

import tf
from tf.msg import tfMessage 
from tf.transformations import euler_from_quaternion

class SelectNavigationGoal(smach.State):
        def __init__(self):
                smach.State.__init__(self,
                        outcomes=['selected','not_selected','failed'],
                        output_keys=['base_pose'])

                self.goals = []

        def execute(self, userdata):
                # defines
                x_min = 0
                x_max = 4.0
                x_increment = 2
                y_min = -4.0
                y_max = 0.0
                y_increment = 2
                th_min = -3.14
                th_max = 3.14
                th_increment = 2*3.1414926/4

                # generate new list, if list is empty
                if len(self.goals) == 0:
                        x = x_min
                        y = y_min
                        th = th_min
                        while x <= x_max:
                                while y <= y_max:
                                        while th <= th_max:
                                                pose = []
                                                pose.append(x) # x
                                                pose.append(y) # y
                                                pose.append(th) # th
                                                self.goals.append(pose)
                                                th += th_increment
                                        y += y_increment
                                        th = th_min
                                x += x_increment
                                y = y_min
                                th = th_min

                #print self.goals
                #userdata.base_pose = self.goals.pop() # takes last element out of list
                userdata.base_pose = self.goals.pop(random.randint(0,len(self.goals)-1)) # takes random element out of list

                return 'selected'


class SkillImplementation(SkillsBase):
	def __init__(self, yamlFile):
		smach.StateMachine.__init__(self, outcomes=['success', 'failed', 'ended', 'reached', 'not_reached'])

		self.main_conditions = yaml.load(open(yamlFile).read())

		self.full_components = ""
		self.required_components = ""
		self.optional_components = ""

		self.check_pre = None
		self.check_post = None

		self.tfL = tf.TransformListener()

		with self:

			self.add('PRECONDITION_CHECK', self.pre_conditions(yamlFile), transitions={'success':'SELECT_GOAL', 'failed':'PRECONDITION_CHECK'})
			self.add('SELECT_GOAL',SelectNavigationGoal(),transitions={'selected':'SKILL_SM','not_selected':'failed','failed':'failed'})
			self.add('SKILL_SM',self.execute_machine(), transitions={'reached':'POSTCONDITION_CHECK', 'failed':'SELECT_GOAL', 'not_reached': 'SELECT_GOAL'})
			self.add('POSTCONDITION_CHECK',self.post_conditions(yamlFile), transitions={'success':'success'})

	def execute_machine(self):
		mach =  skill_state_approachpose.skill_state_approachpose(components = self.check_pre.full_components)
		return mach

# base reports some diagn info 
	def pre_conditions(self, yaml_filename):
		
		self.check_pre = pre_check.PreConditionCheck(self.main_conditions, self.tfL)
		return self.check_pre

	# tf frames comparison : base_link against map
	def post_conditions(self, yaml_filename):

		self.check_post = post_check.PostConditionCheck(self.main_conditions, self.tfL)
		return self.check_post

	@property    
	def inputs(self):
		return "Some Input"
    
	@property
	def outputs(self):
		return "Some Output"

	@property
	def requirements(self):
		return "Some Requirements"
