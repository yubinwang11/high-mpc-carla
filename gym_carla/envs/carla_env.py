#!/usr/bin/env python

# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from __future__ import division

import copy
import numpy as np
import pygame
import random
import time
from skimage.transform import resize

import gym
from gym import spaces
from gym.utils import seeding
import carla

from high_mpc import High_MPC

from gym_carla.envs.render import BirdeyeRender
from gym_carla.envs.route_planner import RoutePlanner
from gym_carla.envs.misc import *


class CarlaEnv(gym.Env):
  """An OpenAI gym wrapper for CARLA simulator."""

  def __init__(self, params):
    # parameters
    self.display_size = params['display_size']  # rendering screen size
    self.max_past_step = params['max_past_step']
    self.number_of_vehicles = params['number_of_vehicles']
    self.number_of_walkers = params['number_of_walkers']
    self.dt = params['dt']
    #self.task_mode = params['task_mode']
    self.max_time_episode = params['max_time_episode']
    self.max_waypt = params['max_waypt']
    self.detect_range = params['detect_range']
    self.detector_num = params['detector_num']
    self.detect_angle = params['detect_angle']
    self.obs_range = params['obs_range']
    self.lidar_bin = params['lidar_bin']
    self.d_behind = params['d_behind']
    #self.obs_size = int(self.obs_range/self.lidar_bin)
    self.out_lane_thres = params['out_lane_thres']
    self.desired_speed = params['desired_speed']
    self.max_ego_spawn_times = params['max_ego_spawn_times']
    self.display_route = params['display_route']
    self.use_render = params['render']
    self.eval = params['eval']
    self.record = params['record']
    if not self.record:
      self.obs_size = int(self.obs_range/self.lidar_bin)
    else:
      self.obs_size = int(self.obs_range/self.lidar_bin) # 1920

    if 'pixor' in params.keys():
      self.pixor = params['pixor']
      self.pixor_size = params['pixor_size']
    else:
      self.pixor = False

    # Destination
    self.dests = None

    # action and observation spaces
    #self.act_high = np.array([20.0, 10.0, np.pi/2, 20.0, 20.0, 20.0, 20.0, 20.0], dtype=np.float32) 
    self.act_high = np.array([50.0, 10.0, np.pi/2, 20.0, 50.0, 50.0, 50.0, 50.0], dtype=np.float32) 
    self.act_low = np.array([-50.0, -10, -np.pi/2, -20.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    #self.act_low = np.array([-20.0, -10, -np.pi/2, -10.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    self.obs_high, self.obs_low = [275.0, 10.0, np.pi/2, 20.0], [0.0, -10, -np.pi/2, -5.0]
    for i in range(self.detector_num):
      self.obs_high.append(50.0)
      self.obs_low.append(0.0)
    self.obs_high = np.array(self.obs_high, dtype=np.float32)
    self.obs_low = np.array(self.obs_low, dtype=np.float32)
    '''
    self.obs_high = np.array([275.0, 10.0, np.pi/2, 20.0, \
                              50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0,\
                              50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0,\
                              50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0], dtype=np.float32)
    self.obs_low = np.array([0.0, -10, -np.pi/2, -5.0,\
                             0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,\
                             0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,\
                             0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    '''
    self.action_space = spaces.Box(
      low=self.act_low, high=self.act_high, dtype=np.float32
      )
    self.observation_space = spaces.Box(low=self.obs_low, high=self.obs_high, dtype=np.float32)

    self.discrete = params['discrete']
    self.discrete_act = [params['discrete_acc'], params['discrete_steer']] # acc, steer
    self.n_acc = len(self.discrete_act[0])
    self.n_steer = len(self.discrete_act[1])
    #if self.discrete:
      #self.action_space = spaces.Discrete(self.n_acc*self.n_steer)
    #else:
      #self.action_space = spaces.Box(np.array([params['continuous_accel_range'][0], 
      #params['continuous_steer_range'][0]]), np.array([params['continuous_accel_range'][1],
      #params['continuous_steer_range'][1]]), dtype=np.float32)  # acc, steer
    #observation_space_dict = {
      #'camera': spaces.Box(low=0, high=255, shape=(self.obs_size, self.obs_size, 3), dtype=np.uint8),
      #'lidar': spaces.Box(low=0, high=255, shape=(self.obs_size, self.obs_size, 3), dtype=np.uint8),
      #'birdeye': spaces.Box(low=0, high=255, shape=(self.obs_size, self.obs_size, 3), dtype=np.uint8),
      #'state': spaces.Box(np.array([-2, -1, -5, 0]), np.array([2, 1, 30, 1]), dtype=np.float32)
      #}
    #if self.pixor:
      #observation_space_dict.update({
        #'roadmap': spaces.Box(low=0, high=255, shape=(self.obs_size, self.obs_size, 3), dtype=np.uint8),
        #'vh_clas': spaces.Box(low=0, high=1, shape=(self.pixor_size, self.pixor_size, 1), dtype=np.float32),
        #'vh_regr': spaces.Box(low=-5, high=5, shape=(self.pixor_size, self.pixor_size, 6), dtype=np.float32),
        ##################'pixor_state': spaces.Box(np.array([-1000, -1000, -1, -1, -5]), np.array([1000, 1000, 1, 1, 20]), dtype=np.float32)
        #})
    #self.observation_space = spaces.Dict(observation_space_dict)

    # Connect to carla server and get world object
    print('connecting to Carla server...')
    client = carla.Client('localhost', params['port'])
    client.set_timeout(10.0) # 10.0
    self.town_id = 'Town05'
    #self.world = client.load_world(params['town'])
    self.world = client.load_world(self.town_id)
    
    print('Carla server connected!')

    self.map = self.world.get_map()

    self.plan_T = 5.0 # Prediction horizon for MPC 
    self.plan_dt = 0.1 # Sampling time step for MPC

    # simulation parameters ....
    self.sim_T = 50          # Episode length, seconds
    self.sim_dt = 0.1       # simulation time step
    self.max_episode_steps = int(self.sim_T/self.sim_dt)
    
    # Set weather
    self.world.set_weather(carla.WeatherParameters.ClearNoon)
    # Get spawn points
    self.vehicle_spawn_points = list(self.world.get_map().get_spawn_points())
    # create the blueprint library
    self.blueprint_library = self.world.get_blueprint_library()

    # read all valid spawn points
    self.all_default_spawn = self.map.get_spawn_points()
    
    self.walker_spawn_points = []
    for i in range(self.number_of_walkers):
      spawn_point = carla.Transform()
      loc = self.world.get_random_location_from_navigation()
      if (loc != None):
        spawn_point.location = loc
        self.walker_spawn_points.append(spawn_point)

    # Create the ego vehicle blueprint
    #self.ego_bp = self._create_vehicle_bluepprint(params['ego_vehicle_filter'], color='49,8,8')
    self.ego_bp = self._create_vehicle_bluepprint(params['ego_vehicle_filter'], color='255,0,0')

    # Collision sensor
    self.collision_hist = [] # The collision history
    self.collision_hist_l = 1 # collision history length
    self.collision_bp = self.world.get_blueprint_library().find('sensor.other.collision')

    # Obstacle detector
    self.distance_measurements = []
    self.obstector_bp = self.world.get_blueprint_library().find('sensor.other.obstacle')
    #self.obstector_trans = carla.Transform(carla.Location(x=0.0, z=1.0))
    self.obstector_bp.set_attribute('debug_linetrace', 'False')
    self.obstector_bp.set_attribute('distance', '50')
    self.obstector_bp.set_attribute('hit_radius', '0.2') #0.5
    
    '''
    # Lidar sensor
    self.lidar_data = None
    self.lidar_height = 2.1
    self.lidar_trans = carla.Transform(carla.Location(x=0.0, z=self.lidar_height))
    self.lidar_bp = self.world.get_blueprint_library().find('sensor.lidar.ray_cast')
    self.lidar_bp.set_attribute('channels', '32')
    self.lidar_bp.set_attribute('range', '5000')
    '''

    '''
    # Radar sensor
    self.radar_data = None
    self.radar_trans = carla.Transform(carla.Location(x=0.0, z=1.0))
    self.radar_bp = self.world.get_blueprint_library().find('sensor.other.radar')
    self.radar_bp.set_attribute('horizontal_fov', '180')
    #self.lidar_bp.set_attribute('range', '30')
    '''

    # Camera sensor
    self.camera_img = np.zeros((self.obs_size, self.obs_size, 3), dtype=np.uint8)
    #self.camera_trans = carla.Transform(carla.Location(x=0.8, z=1.7))
    self.camera_trans = carla.Transform(carla.Location(x=-6.0, z=2.5))
    self.camera_bp = self.world.get_blueprint_library().find('sensor.camera.rgb')
    # Modify the attributes of the blueprint to set image resolution and field of view.
    self.camera_bp.set_attribute('image_size_x', str(self.obs_size))
    self.camera_bp.set_attribute('image_size_y', str(self.obs_size))
    #self.camera_bp.set_attribute('fov', '110')
    self.camera_bp.set_attribute('fov', '70')
    # Set the time in seconds between sensor captures
    self.camera_bp.set_attribute('sensor_tick', '0.02')

    # Set fixed simulation step for synchronous mode
    self.settings = self.world.get_settings()
    self.settings.fixed_delta_seconds = self.dt

    # Record the time of total steps and resetting steps
    self.reset_step = 0
    self.total_step = 0
    
    # Initialize the renderer
    if self.use_render:
      self._init_renderer()

    # Get pixel grid points
    if self.pixor:
      x, y = np.meshgrid(np.arange(self.pixor_size), np.arange(self.pixor_size)) # make a canvas with coordinates
      x, y = x.flatten(), y.flatten()
      self.pixel_grid = np.vstack((x, y)).T

    if self.eval:
      self.noise_bound = 0.5
    else:
      self.noise_bound = 5

  def reset(self):

    # Delete sensors, vehicles and walkers
    #self._clear_all_actors(['vehicle.*', 'controller.ai.walker', 'walker.*'])
    
    # Clear sensor objects  
    self.collision_sensor = None
    #self.lidar_sensor = None
    self.camera_sensor = None
    self.detector_list = None

    self._clear_all_actors(['sensor.other.collision', 'sensor.other.obstacle', 'sensor.lidar.ray_cast', \
                           'sensor.camera.rgb', 'vehicle.*', 'controller.ai.walker', 'walker.*'])
    
    # reset time
    self.t = 0
    # reset reward
    self.reward = 0
    # reset done
    self.done = False
    self.arrived = False
    self.out_of_time = False
    self.collided = False
    self.prev_decision_var = None

    self.inter_axle_distance = None

    # Disable sync mode
    self._set_synchronous_mode(True) # True

    # Spawn surrounding vehicles
    random.shuffle(self.vehicle_spawn_points)
    count = self.number_of_vehicles
    if count > 0:
      for spawn_point in self.vehicle_spawn_points:
        if self._try_spawn_random_vehicle_at(spawn_point, number_of_wheels=[4]):
          count -= 1
        if count <= 0:
          break
    while count > 0:
      if self._try_spawn_random_vehicle_at(random.choice(self.vehicle_spawn_points), number_of_wheels=[4]):
        count -= 1

    
    # Spawn pedestrians
    random.shuffle(self.walker_spawn_points)
    count = self.number_of_walkers
    if count > 0:
      for spawn_point in self.walker_spawn_points:
        if self._try_spawn_random_walker_at(spawn_point):
          count -= 1
        if count <= 0:
          break
    while count > 0:
      if self._try_spawn_random_walker_at(random.choice(self.walker_spawn_points)):
        count -= 1
    
    # Get actors polygon list
    self.vehicle_polygons = []
    vehicle_poly_dict = self._get_actor_polygons('vehicle.*')
    self.vehicle_polygons.append(vehicle_poly_dict)
    self.walker_polygons = []
    walker_poly_dict = self._get_actor_polygons('walker.*')
    self.walker_polygons.append(walker_poly_dict)
    
    # Spawn the ego vehicle
    ego_spawn_times = 0
    while True:
      if ego_spawn_times > self.max_ego_spawn_times:
        self.reset()

   
      transform = self.all_default_spawn[155] 
      if self._try_spawn_ego_vehicle_at(transform):
        break
      else:
        ego_spawn_times += 1
        time.sleep(0.1)

    ## vehicle param
    self.startpoint = self.map.get_waypoint(self.ego.get_location(), project_to_road=True)
    self.lane_width = self.startpoint.lane_width
    
    self.road_bound_abs = 1.5 * self.lane_width

    self.vehicle_length = self.ego.bounding_box.extent.x * 2
    self.vehicle_width = self.ego.bounding_box.extent.y * 2 # actually use  length to estimate width with buffer
      
    self.inter_axle_distance = 2*self.ego.bounding_box.extent.x

    # determine and visualize the destination
    self.goal_state = np.array([275, 0, 0, 8]).tolist() # 275
    self.destination = self.all_default_spawn[255] 
    self.dests = self.goal_state
    self.road_len = self.goal_state[0]
    self.world.debug.draw_point(self.destination.location, size=0.3, color=carla.Color(255,0,0), life_time=300)
    
    # spawn the moving obstacles (agents)
    self.moving_agents = []
    #self.lane_id_list = [-3, -2, -1, -1, -2, -2, -3, -1, -3] #self.lane_id_list = [-3, -1, -1, -1, -2, -2, -2]
    self.s_list = [15+random.uniform(-self.noise_bound,self.noise_bound), 30+random.uniform(-self.noise_bound,self.noise_bound), \
                    45+random.uniform(-self.noise_bound,self.noise_bound), 60+random.uniform(-self.noise_bound,self.noise_bound), \
                    75+random.uniform(-self.noise_bound,self.noise_bound), 90+random.uniform(-self.noise_bound,self.noise_bound), \
                      105+random.uniform(-self.noise_bound,self.noise_bound),120+random.uniform(-self.noise_bound,self.noise_bound), \
                        135+random.uniform(-self.noise_bound,self.noise_bound) ] #self.s_list = [30, 60, 80, 100, 100, 80, 120]
    for i in range(len(self.s_list)):
      if i > 0:
        distance_agents = self.s_list[i] - self.s_list[i-1]
        if distance_agents <= 6:
          distance_refinement = 6-distance_agents
          self.s_list[i-1] -= distance_refinement / 2 
          self.s_list[i] += distance_refinement / 2 
          
    self.road_id = 34
    self.center_lane_id = -2

    self.num_agents = len(self.s_list)
    #self.num_agents = 0

    for i in range(self.num_agents):
        spawn_lane_id = -random.randint(1,3)
        #print(spawn_lane_id)
        agent_waypoint = self.map.get_waypoint_xodr(self.road_id, spawn_lane_id, self.s_list[i])
        spawn_agent_transform = carla.Transform(location=carla.Location(x=agent_waypoint.transform.location.x, \
                                    y=agent_waypoint.transform.location.y, z=agent_waypoint.transform.location.z+0.5),\
                                                    rotation=agent_waypoint.transform.rotation)
        #print(rand_lane_id, rand_s)
        moving_agent = self.spawn_autopilot_agent(self.blueprint_library, self.world, spawn_agent_transform)
        self.moving_agents.append(moving_agent)

    # Add collision sensor
    self.collision_sensor = self.world.spawn_actor(self.collision_bp, carla.Transform(), attach_to=self.ego)
    self.collision_sensor.listen(lambda event: get_collision_hist(event))
    def get_collision_hist(event):
      impulse = event.normal_impulse
      intensity = np.sqrt(impulse.x**2 + impulse.y**2 + impulse.z**2)
      self.collision_hist.append(intensity)
      if len(self.collision_hist)>self.collision_hist_l:
        self.collision_hist.pop(0)
    self.collision_hist = []
    
    # Add obstacle dector
    self.distance_measurements = [] #self.det_range
    self.detector_list = []

    for detector_i in range(self.detector_num):
      self.distance_measurements.append(self.detect_range)
      self.obstector_trans = carla.Transform(carla.Location(x=0.0, z=0.5), carla.Rotation(yaw=-self.detect_angle/2+(self.detect_angle/(self.detector_num-1))*detector_i))

      self.detector_list.append(self.world.spawn_actor(self.obstector_bp, self.obstector_trans, attach_to=self.ego))
      #self.detector_list[detector_i].listen(lambda distance_i: get_obstacle_distance(distance_i, detector_i))

      self.listen_dector_distance(detector_i)

    # Add camera sensor
    self.camera_sensor = self.world.spawn_actor(self.camera_bp, self.camera_trans, attach_to=self.ego)
    self.camera_sensor.listen(lambda data: get_camera_img(data))
    def get_camera_img(data):
      array = np.frombuffer(data.raw_data, dtype = np.dtype("uint8"))
      array = np.reshape(array, (data.height, data.width, 4))
      array = array[:, :, :3]
      array = array[:, :, ::-1]
      self.camera_img = array

    # Update timesteps
    self.time_step=0
    self.reset_step+=1

    # Enable sync mode
    self.settings.synchronous_mode = True
    if not self.record:
      self.settings.no_rendering_mode = True
    self.world.apply_settings(self.settings)

    self.routeplanner = RoutePlanner(self.ego, self.max_waypt)
    self.waypoints, _, self.vehicle_front = self.routeplanner.run_step()
    #self.waypoints = self.map.get_waypoint(self.ego.get_location())

    # Set ego information for render
    if self.use_render:
      self.birdeye_render.set_hero(self.ego, self.ego.id)

    obs = self._get_obs()

    self.travelled_dist = None

    self.high_mpc = High_MPC(T=self.plan_T, dt=self.plan_dt, L=self.inter_axle_distance, vehicle_length=self.vehicle_length,\
                            vehicle_width = self.vehicle_width, lane_width = self.lane_width,  init_state=self.ego_state)

    return obs
  
  def step(self, action):

    if self.eval:
      # top view
      self.spectator = self.world.get_spectator()
      transform = self.ego.get_transform()
      self.spectator.set_transform(carla.Transform(transform.location + carla.Location(z=30),
                                              carla.Rotation(pitch=-90)))
        
    # Calculate acceleration and steering
    if self.discrete:
      acc = self.discrete_act[0][action//self.n_steer]
      steer = self.discrete_act[1][action%self.n_steer]
    else:
      acc = action[0]
      steer = -action[1]

    
    # Convert acceleration to throttle and brake
    if acc > 0:
      throttle = np.clip(acc/3,0,1) # np.clip(acc/3,0,1) 
      brake = 0
    else:
      throttle = 0
      brake = np.clip(-acc/8,0,1)
    
    # Apply control
    act = carla.VehicleControl(throttle=float(throttle), steer=float(steer), brake=float(brake))
    #print(act)
    self.ego.apply_control(act)

    self.world.tick()

    # Append actors polygon list
    vehicle_poly_dict = self._get_actor_polygons('vehicle.*')
    self.vehicle_polygons.append(vehicle_poly_dict)
    while len(self.vehicle_polygons) > self.max_past_step:
      self.vehicle_polygons.pop(0)
    walker_poly_dict = self._get_actor_polygons('walker.*')
    self.walker_polygons.append(walker_poly_dict)
    while len(self.walker_polygons) > self.max_past_step:
      self.walker_polygons.pop(0)

    # Update timesteps
    self.t += self.sim_dt
    self.time_step += 1
    self.total_step += 1

    obs = self._get_obs()
    # state information
    info = {
      #'waypoints': self.curr_waypoint,
      'ego_state': self.ego_state
    }

    self.done = self._terminal()
    r = self._get_reward()
    
    #if self.done:
      # Delete sensors, vehicles and walkers
      #self._clear_all_actors(['sensor.other.collision', 'sensor.other.obstacle', 'sensor.lidar.ray_cast', \
                            #'sensor.camera.rgb']), 
                            # 'vehicle.*', 'controller.ai.walker', 'walker.*'])
      #self.camera_sensor.destroy()
      #self.collision_sensor.destroy()
      #for i in range(len(self.detector_list)):
        #self.detector_list[i].destroy()
      

    return obs,  r, self.done, copy.deepcopy(info) #(obs,  r, self.done, copy.deepcopy(info))

  def seed(self, seed=None):
    self.np_random, seed = seeding.np_random(seed)
    return [seed]

  def render(self):
    #pass
    #self.birdeye_render.render(self.display)
    frame = pygame.surfarray.array3d(self.display)
    return frame
  
  def _create_vehicle_bluepprint(self, actor_filter, color=None, number_of_wheels=[4]):
    """Create the blueprint for a specific actor type.

    Args:
      actor_filter: a string indicating the actor type, e.g, 'vehicle.lincoln*'.

    Returns:
      bp: the blueprint object of carla.
    """
    blueprints = self.world.get_blueprint_library().filter(actor_filter)
    blueprint_library = []
    for nw in number_of_wheels:
      blueprint_library = blueprint_library + [x for x in blueprints if int(x.get_attribute('number_of_wheels')) == nw]
    bp = random.choice(blueprint_library)
    if bp.has_attribute('color'):
      if not color:
        color = random.choice(bp.get_attribute('color').recommended_values)
      bp.set_attribute('color', color)
    return bp

  def _init_renderer(self):
    """Initialize the birdeye view renderer.
    """
    pygame.init()
    self.display = pygame.display.set_mode(
    (self.display_size*2, self.display_size), # * 3
    pygame.HWSURFACE | pygame.DOUBLEBUF)

    pixels_per_meter = self.display_size / self.obs_range
    pixels_ahead_vehicle = (self.obs_range/2 - self.d_behind) * pixels_per_meter
    birdeye_params = {
      'screen_size': [self.display_size, self.display_size],
      'pixels_per_meter': pixels_per_meter,
      'pixels_ahead_vehicle': pixels_ahead_vehicle
    }
    self.birdeye_render = BirdeyeRender(self.world, birdeye_params)

  def _set_synchronous_mode(self, synchronous = True):
    """Set whether to use the synchronous mode.
    """
    self.settings.synchronous_mode = synchronous
    self.world.apply_settings(self.settings)

  def _try_spawn_random_vehicle_at(self, transform, number_of_wheels=[4]):
    """Try to spawn a surrounding vehicle at specific transform with random bluprint.

    Args:
      transform: the carla transform object.

    Returns:
      Bool indicating whether the spawn is successful.
    """
    blueprint = self._create_vehicle_bluepprint('vehicle.*', number_of_wheels=number_of_wheels)
    blueprint.set_attribute('role_name', 'autopilot')
    vehicle = self.world.try_spawn_actor(blueprint, transform)
    if vehicle is not None:
      vehicle.set_autopilot()
      return True
    return False

  def _try_spawn_random_walker_at(self, transform):
    """Try to spawn a walker at specific transform with random bluprint.

    Args:
      transform: the carla transform object.

    Returns:
      Bool indicating whether the spawn is successful.
    """
    walker_bp = random.choice(self.world.get_blueprint_library().filter('walker.*'))
    # set as not invencible
    if walker_bp.has_attribute('is_invincible'):
      walker_bp.set_attribute('is_invincible', 'false')
    walker_actor = self.world.try_spawn_actor(walker_bp, transform)

    if walker_actor is not None:
      walker_controller_bp = self.world.get_blueprint_library().find('controller.ai.walker')
      walker_controller_actor = self.world.spawn_actor(walker_controller_bp, carla.Transform(), walker_actor)
      # start walker
      walker_controller_actor.start()
      # set walk to random point
      walker_controller_actor.go_to_location(self.world.get_random_location_from_navigation())
      # random max speed
      walker_controller_actor.set_max_speed(1 + random.random())    # max speed between 1 and 2 (default is 1.4 m/s)
      return True
    return False

  def _try_spawn_ego_vehicle_at(self, transform):
    """Try to spawn the ego vehicle at specific transform.
    Args:
      transform: the carla transform object.
    Returns:
      Bool indicating whether the spawn is successful.
    """
    vehicle = None
    # Check if ego position overlaps with surrounding vehicles
    overlap = False
    for idx, poly in self.vehicle_polygons[-1].items():
      poly_center = np.mean(poly, axis=0)
      ego_center = np.array([transform.location.x, transform.location.y])
      dis = np.linalg.norm(poly_center - ego_center)
      if dis > 8:
        continue
      else:
        overlap = True
        break

    if not overlap:
      vehicle = self.world.try_spawn_actor(self.ego_bp, transform)

    if vehicle is not None:
      self.ego=vehicle
      return True
      
    return False

  def _get_actor_polygons(self, filt):
    """Get the bounding box polygon of actors.

    Args:
      filt: the filter indicating what type of actors we'll look at.

    Returns:
      actor_poly_dict: a dictionary containing the bounding boxes of specific actors.
    """
    actor_poly_dict={}
    for actor in self.world.get_actors().filter(filt):
      # Get x, y and yaw of the actor
      trans=actor.get_transform()
      x=trans.location.x
      y=trans.location.y
      yaw=trans.rotation.yaw/180*np.pi
      # Get length and width
      bb=actor.bounding_box
      l=bb.extent.x
      w=bb.extent.y
      # Get bounding box polygon in the actor's local coordinate
      poly_local=np.array([[l,w],[l,-w],[-l,-w],[-l,w]]).transpose()
      # Get rotation matrix to transform to global coordinate
      R=np.array([[np.cos(yaw),-np.sin(yaw)],[np.sin(yaw),np.cos(yaw)]])
      # Get global bounding box polygon
      poly=np.matmul(R,poly_local).transpose()+np.repeat([[x,y]],4,axis=0)
      actor_poly_dict[actor.id]=poly
    return actor_poly_dict

  def _get_obs(self):
    """Get the observations."""
    if self.use_render:
      ## Birdeye rendering
      self.birdeye_render.vehicle_polygons = self.vehicle_polygons
      self.birdeye_render.walker_polygons = self.walker_polygons
      self.birdeye_render.waypoints = self.waypoints

      # birdeye view with roadmap and actors
      birdeye_render_types = ['roadmap', 'actors']
      #if self.display_route:
        #birdeye_render_types.append('waypoints')
      
      self.birdeye_render.render(self.display, birdeye_render_types)
      birdeye = pygame.surfarray.array3d(self.display)
      birdeye = birdeye[0:self.display_size, :, :]
      birdeye = display_to_rgb(birdeye, self.obs_size)

      # Roadmap
      if self.pixor:
        roadmap_render_types = ['roadmap']
        if self.display_route:
          roadmap_render_types.append('waypoints')
        self.birdeye_render.render(self.display, roadmap_render_types)
        roadmap = pygame.surfarray.array3d(self.display)
        roadmap = roadmap[0:self.display_size, :, :]
        roadmap = display_to_rgb(roadmap, self.obs_size)
        # Add ego vehicle
        for i in range(self.obs_size):
          for j in range(self.obs_size):
            if abs(birdeye[i, j, 0] - 255)<20 and abs(birdeye[i, j, 1] - 0)<20 and abs(birdeye[i, j, 0] - 255)<20:
              roadmap[i, j, :] = birdeye[i, j, :]

      # Display birdeye image
      birdeye_surface = rgb_to_display_surface(birdeye, self.display_size)
      self.display.blit(birdeye_surface, (0, 0))
      
      ## Display camera image
      camera = resize(self.camera_img, (self.obs_size, self.obs_size)) * 255
      camera_surface = rgb_to_display_surface(camera, self.display_size)
      self.display.blit(camera_surface, (self.display_size, 0)) # self.display_size * 2
      
      # Display on pygame
      pygame.display.flip()

    self.ego_state = self.get_state_frenet(self.ego, self.map)

    #radar_data = self.radar_data
    obs = []
    #obs += [np.array(self.goal_state[0])-np.array(self.ego_state[0])]
    #obs += self.ego_state[1:]
    obs += self.ego_state
    obs += self.distance_measurements

    obs = np.array(obs)

    return obs

  def _get_roatation_matrix(self,yaw):
        return np.array([[np.cos(yaw), -np.sin(yaw)], [np.sin(yaw), np.cos(yaw)]])
  
  def _get_reward(self):

    """Calculate the reward."""
    # reward for speed tracking
    v = self.ego.get_velocity()
    speed = np.sqrt(v.x**2 + v.y**2)
    max_speed = 10
    #r_speed = -abs(speed - self.desired_speed)
    r_speed = 0
    if speed >= 8:
      r_speed = speed / max_speed
    
    
    # reward for collision
    r_collision = 0
    if len(self.collision_hist) > 0:
      r_collision = -100
      #r_collision = -0.01*self.collision_hist[0]

    # reward for steering:
    r_steer = -abs(self.ego.get_control().steer)  # **2
    #r_steer = 0

    r_arrive = 0
    #if self.arrived:
      #r_arrive = 50

    r_speed_ep = 0
    if self.arrived:
      #r_speed += 10* (self.road_len / self.t - 3)
      r_speed_ep += self.road_len / self.t 

    r_time = 0 
    if self.out_of_time:
      r_time -= 100

    # reward for how long travelled
    #r_s = self.ego_state[0] - self.prev_state[0]
    r_forward = 0 
    current_dist = self.ego_state[0]
    if self.travelled_dist is not None:
      r_forward = current_dist - self.travelled_dist#self.ego_state[0] / 20

    self.travelled_dist = current_dist

    # cost for out of road
    r_road = 0
    ego_rotation = self._get_roatation_matrix(self.ego_state[2])
    for corner_id in range(4):
      if corner_id == 0:
          alpha = np.array([self.vehicle_width/2, self.vehicle_length/2]).T
      elif corner_id == 1:
          alpha = np.array([self.vehicle_width/2, -self.vehicle_length/2]).T
      elif corner_id == 2:
          alpha = np.array([-self.vehicle_width/2, -self.vehicle_length/2]).T
      else:
          alpha = np.array([-self.vehicle_width/2, self.vehicle_length/2]).T
      
      corner_pos = self.ego_state[:2] + ego_rotation @ alpha

      if abs(corner_pos[1]) >=self.road_bound_abs:
        dist_road = abs(abs(corner_pos[1]) - self.road_bound_abs)
        r_road = -dist_road
      
    #r = 200*r_collision + 1*lspeed_lon + 10*r_fast + 1*r_out + r_steer*5 + 0.2*r_lat - 0.1+  r_arrive + 10 * r_speed + 5 * r_s
    #r = 200 * r_collision + 30 * r_speed + 0.1 * r_s + r_arrive + 10 * r_lane + 1 * r_road + r_time
    r = r_collision + r_time + r_forward + r_steer + r_arrive + r_speed + r_speed_ep + r_road

    #self.reward += r
  
    return r

  def _terminal(self):
    """Calculate whether to terminate the current episode."""
    # Get ego state

    # If collides
    if len(self.collision_hist)>0: 
      print('end with collision')
      self.collided = True
      return True

    # If reach maximum timestep
    if self.time_step>self.max_time_episode:
      print('end with time')
      self.out_of_time = True
      return True

    if self.dests is not None:
      #dist2desti = np.linalg.norm(np.array(self.goal_state[:3]) - np.array(state[:3]))
      #if dist2desti < 1:
      if self.ego_state[0] >= self.goal_state[0]-2:
        self.arrived = True
        return True
      
    return False

  def _clear_all_actors(self, actor_filters):
    """Clear specific actors."""
    for actor_filter in actor_filters:
      for actor in self.world.get_actors().filter(actor_filter):
        #if actor.is_alive:
          #if actor.type_id == 'controller.ai.walker':
           # actor.stop()
        actor.destroy()

  def get_longitudinal_speed(self, vehicle):
    velocity = vehicle.get_velocity()
    forward_vector = vehicle.get_transform().get_forward_vector()
    longitudinal_speed = np.dot(np.array([velocity.x, -velocity.y, velocity.z]), np.array([forward_vector.x,  -forward_vector.y, forward_vector.z]))

    return longitudinal_speed
  
  def get_state_frenet(self, vehicle, map):

    x = map.get_waypoint(vehicle.get_location(), project_to_road=True).s
    centerline_waypoint= map.get_waypoint_xodr(self.road_id,self.center_lane_id, x) # road and lane id
    if centerline_waypoint is None:
      centerline_waypoint = map.get_waypoint(vehicle.get_location(), project_to_road=True)
    tangent_vector = centerline_waypoint.transform.get_forward_vector()
    normal_vector = carla.Vector2D(-(-tangent_vector.y), tangent_vector.x)
    #normal_vector_normalized = np.array([normal_vector.x, -normal_vector.y]) /  np.linalg.norm(np.array([normal_vector.x, -normal_vector.y]))
    norm_normal_vector = np.linalg.norm(np.array([normal_vector.x, normal_vector.y])) 
    normal_vector_normalized = 1 / norm_normal_vector * np.array([normal_vector.x, normal_vector.y]).T
    y_hat = np.array([vehicle.get_location().x-centerline_waypoint.transform.location.x, 
                                    -vehicle.get_location().y-(-centerline_waypoint.transform.location.y)])
    y = np.dot(normal_vector_normalized, y_hat)
    forward_angle = np.arctan2(-tangent_vector.y, tangent_vector.x) * 180/np.pi
    if -180 <= forward_angle < 0:
        forward_angle += 360
    global_yaw = -vehicle.get_transform().rotation.yaw
    if -180 <= global_yaw < 0:
        global_yaw += 360
  
    #yaw = (forward_angle - global_yaw )/180 * np.pi
    yaw = (global_yaw-forward_angle)/180 * np.pi
    speed = self.get_longitudinal_speed(vehicle)
    vehicle_state =np.array([x, y, yaw, speed]).tolist()

    return  vehicle_state
  
  def spawn_autopilot_agent(self, blueprint_lib, world, spawn_transform):

    agent_bp = random.choice(blueprint_lib.filter('vehicle.*'))
    #agent_bp = blueprint_lib.find('vehicle.tesla.model3')
    #rand_r, rand_g, rand_b = random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)
    #agent_bp.set_attribute('color', '{},{},{}'.format(rand_r, rand_g, rand_b))
    agent_bp.set_attribute('role_name', 'autopilot')
    agent = world.spawn_actor(agent_bp, spawn_transform)
    agent.set_autopilot(True)

    return agent
  
  def listen_dector_distance(self, line_i):
    self.detector_list[line_i].listen(lambda distance: get_obstacle_distance(distance, line_i))
    def get_obstacle_distance(info, detector_i):
      if info is not None:
        self.distance_measurements[detector_i] = info.distance
      else:
        self.distance_measurements[detector_i] = self.detect_range #carla.ObstacleDetectionEvent(distance=self.det_range)



