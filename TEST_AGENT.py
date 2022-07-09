import torch
from torch import nn
from torch._C import device
from torch import optim
import numpy as np
from collections import deque
from wandb import wandb
from graphs import graph
import gym
import gym_ple
import vizdoomgym
import DRQN
import DQN
import CNN
import hyperparameters
from process_state import check_if_enemy_in_obs, getFrame, clip_reward, makeState
import time

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using {device} device")
torch.autograd.set_detect_anomaly(True)

def test(game):
    env = gym.make(game)
    y = CNN.NeuralNetwork_Recurrent(env.action_space.n, None).to(device)
    y_navigator = CNN.NeuralNetwork_Forward(3, None).to(device)
    actor = DRQN.DRQN(hyperparameters.REPLAY_MEMORY_SIZE, hyperparameters.BATCH_SIZE, hyperparameters.GAMMA, hyperparameters.EPSILON, hyperparameters.EPSILON_MIN, hyperparameters.EPSILON_DECAY)
    navigator = DQN.DQN(hyperparameters.REPLAY_MEMORY_SIZE, hyperparameters.BATCH_SIZE, hyperparameters.GAMMA, hyperparameters.EPSILON, hyperparameters.EPSILON_MIN, hyperparameters.EPSILON_DECAY)
    actor.loadModel(y,'actor.pth')
    navigator.loadModel(y_navigator,'navigato.pth')
    print(y)
    lives = 0
    score = 0
    obs,labels = env.reset()
    obs = getFrame(obs)
    rewards = []
    avgrewards = []
    cumureward = 0
    games = 1
    h = torch.zeros([1,1, 512])
    c  = torch.zeros([1,1, 512])
    total_kills = 0
    total_games = 0
    steps = 0
    preds = 0
    correct = 0
    while True:
        enemy_in_frame = check_if_enemy_in_obs(labels)
        enemy_frame = torch.unsqueeze(torch.unsqueeze(torch.from_numpy(np.expand_dims(obs, axis=0)),axis = 0),axis = 0)
        pred_output = y.forward2(enemy_frame / 255)
        pred_output_p = y.sigmoid(pred_output)
        pred_labels = (pred_output_p > 0.5).float()
        if pred_labels.item() == enemy_in_frame:
            correct += 1
        if pred_labels.item() == 1.0:
            action, h, c = actor.getPrediction(obs /255,y, h, c)
        else:
            action = navigator.getPrediction(obs / 255, y_navigator)
        for i in range(hyperparameters.FRAME_SKIP):
            obs, reward, reward2, done, info, labels = env.step(action)
            if done:
                break
        obs = getFrame(obs)
        cumureward += reward
        kills = info["frags"]
        deaths = info["deaths"]
        env.render()
        steps += 1
        time.sleep(1/30)
        #if info["ale.lives"] < lives:
        #    done = True
        #    lives -= 1
        if done and lives == 0:
            total_kills += kills
            total_games += 1
            lives = 0
            print(steps)
            steps = 0
            obs, labels = env.reset()
            obs = getFrame(obs)
            h = torch.zeros([1,1, 512])
            c  = torch.zeros([1,1, 512])
            #obs, reward, done, info = env.step(1)
            print("Score: ", cumureward, " Game: " , games, " kills ", kills,  "deaths", deaths, "avg kills", total_kills/total_games, "accuracy", correct/preds)
            score = 0
            rewards.append(cumureward)
            avgrewards.append(np.sum(np.array(rewards))/games)
            cumureward = 0
            games += 1
        if games == 100:
            break
    print(np.sum(np.array(rewards))/games)

if __name__ == "__main__":
    #game = 'BreakoutDeterministic-v4'
    #game = "SpaceInvadersDeterministic-v4"
    #game = "PongDeterministic-v4"
    #game = "RobotankDeterministic-v4"
    #game = "VizdoomDefendCenter-v0"
    #game = "VizdoomPredictPosition-v0"
    #game = "VizdoomHealthGathering-v0"
    game = "VizdoomDeathmatch-v0"
    #game = 'FlappyBird-v0'
    test(game)