import numpy as np
import time
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from functools import partial
import argparse

import torch
from torch import nn

from learning_mpc.intersection.mpc_intersection import High_MPC
from learning_mpc.intersection.intersection_env import IntersectionEnv
from learning_mpc.intersection.animation_intersection import SimVisual
from learning_mpc.intersection.networks import DNN

class Worker:

    def __init__(self, env,goal):
        self.env = env
        self.goal = goal
    
    def run_episode(self, model):
        
        obs = self.env.obs
        #obs=self.env.reset(self.goal)
        t, n = 0, 0
        t0 = time.time()
        arrived = False
    
        while t < self.env.sim_T:
            t = self.env.sim_dt * n

            high_variable = model.forward(torch.tensor(obs))
            high_variable = high_variable.detach().numpy().tolist()
            #print("current obs: ", obs)
            #print("current high_variable: ", high_variable)
            obs, reward,  done, info = self.env.step(high_variable)
            print("current reward: ", reward)

            #vehicle_pos = np.array(info['quad_s0'][0:3])
            vehicle_pos = np.array(info['vehicle_state'][0:2])
            goal_pos = self.goal[0:2]
            #print("current pos: ", vehicle_pos, "goal pos: ", goal_pos)
            if (done):
                arrived = True
                break
                plt.close()
            #t_now = time.time()
            #print(t_now - t0)
            #t0 = time.time()
            n += 1
            update = False
            if t > self.env.sim_T:
                    update = True
            yield [info, t, update]
        print("arrvied: ", arrived)