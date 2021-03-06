import torch
from torch import nn
from torch._C import device
from torch import optim
import numpy as np
from collections import deque
from wandb import wandb
import gym
import gym_ple
import vizdoomgym
import DRQN
import DQN
import CNN
from process_state import ammo_left, check_if_enemy_in_obs, clip_reward, makeState, getFrame
import hyperparameters
import time
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using {device} device")
torch.autograd.set_detect_anomaly(True)



def train(game):
    env = gym.make(game)
    y = CNN.NeuralNetwork_Recurrent(env.action_space.n, None).to(device)
    target_y = CNN.NeuralNetwork_Recurrent(env.action_space.n, None).to(device)
    y_navigator = CNN.NeuralNetwork_Forward(3, None).to(device)
    y_navigator_target = CNN.NeuralNetwork_Forward(3, None).to(device)
    loss_fn = nn.HuberLoss()
    loss_fn_detector = nn.BCEWithLogitsLoss()
    optimizer = optim.Adam(y.parameters(), lr = hyperparameters.learning_rate)
    optimizer_navi = optim.Adam(y_navigator.parameters(), lr = hyperparameters.learning_rate)
    actor = DRQN.DRQN(hyperparameters.REPLAY_MEMORY_SIZE, hyperparameters.BATCH_SIZE, hyperparameters.GAMMA, hyperparameters.EPSILON, hyperparameters.EPSILON_MIN, hyperparameters.EPSILON_DECAY)
    navigator = DQN.DQN(hyperparameters.REPLAY_MEMORY_SIZE, hyperparameters.BATCH_SIZE, hyperparameters.GAMMA, hyperparameters.EPSILON, hyperparameters.EPSILON_MIN, hyperparameters.EPSILON_DECAY)
    state = deque(maxlen = 4)
    print(y)
    answer = input("Use a pre-trained model y/n? ")
    if answer == "y":
        actor.loadModel(y,'actor.pth')
        navigator.loadModel(y_navigator, 'navigato.pth')
    frames_seen = 0
    rewards = []
    avgrewards = []
    wandb.init(project="DRQN_" +game, entity="neuroori") 
    games_played = 0
    total_kills = 0
    ammo = np.zeros(10)
    weapon = np.zeros(10)
    for episode in range(1,hyperparameters.EPISODES+500000000000):
        loss = loss_navi = accuracy= None
        obs,labels = env.reset()
        obs = getFrame(obs)
        state.append(obs)
        state.append(obs)
        state.append(obs)
        state.append(obs)
        cumureward = 0
        cumureward2 = 0
        kills = 0 ## 5 for breakout, 3 for spaceinvaders, 0 for pong, 3 for robotank :D
        h = torch.zeros([1,1, 512])
        c  = torch.zeros([1,1, 512])
        preds = 0
        correct = 0
        pred_enemy = 0
        pred_not_enemy = 0
        pred_enemy_correct = 0
        pred_not_enemy_correct = 0
        while True:
            obs_prev = obs
            enemy_in_frame = check_if_enemy_in_obs(labels)
            enemy_in_frame_pred = torch.unsqueeze(torch.unsqueeze(torch.from_numpy(np.expand_dims(obs, axis=0)),axis = 0),axis = 0)
            pred_output = y.forward2(enemy_in_frame_pred / 255)
            pred_output_p = y.sigmoid(pred_output)
            pred_labels = (pred_output_p > 0.5).float()
            preds += 1
            if pred_labels.item() == 1.0:
                pred_enemy += 1
            if pred_labels.item() == 0.0:
                pred_not_enemy += 1
            if pred_labels.item() == enemy_in_frame:
                correct += 1
            if enemy_in_frame == 1.0 and pred_labels.item() == enemy_in_frame:
                pred_enemy_correct += 1
            if enemy_in_frame == 0.0 and pred_labels.item() == enemy_in_frame:
                pred_not_enemy_correct += 1
            if pred_labels.item() == 1.0 and ammo_left(weapon, ammo) is True:
                action, h, c = actor.getPrediction(obs /255,y, h, c)
            else:
                action = navigator.getPrediction(makeState(state) / 255, y_navigator)
            ##Repeat same action four times for flappybird/doom otherwise set it to one.
            for repeat in range(hyperparameters.FRAME_SKIP):
                obs, reward, reward2, done, info, labels, ammo, weapon= env.step(action)
                if done:
                    break
            kills = info["frags"]
            deaths = info["deaths"]
            ##uncomment for atari
            #if info["ale.lives"] < lives:
            #    done = True
            #    lives -= 1
            obs = getFrame(obs)
            cache = state.copy()
            state.append(obs)
            #env.render()
            #agent.update_replay_memory((obs_prev, action, clip_reward(reward), obs , done))
            #if pred_labels.item() == 1.0 or (enemy_in_frame == 1.0 and  frames_seen < 250000):
            if pred_labels.item() == 1.0 or frames_seen < 50000:
                actor.update_replay_memory((obs_prev, action, reward, obs , done, enemy_in_frame))
            if action == 3 or action == 4 or action == 5:
                navigator.update_replay_memory((makeState(cache), action, reward2, makeState(state) , done))
            ##Train the agent
            if len(actor.replay_memory) >= hyperparameters.START_TRAINING_AT_STEP and frames_seen % hyperparameters.TRAINING_FREQUENCY == 0:
                loss, accuracy = actor.train(y, target_y, loss_fn, loss_fn_detector,  optimizer)
                loss_navi = navigator.train(y_navigator, y_navigator_target, loss_fn,  optimizer_navi)
            ##Update target network  
            if len(actor.replay_memory) >= hyperparameters.START_TRAINING_AT_STEP and frames_seen % hyperparameters.TARGET_NET_UPDATE_FREQUENCY == 0:
                target_y.load_state_dict(y.state_dict())
                y_navigator_target.load_state_dict(y_navigator.state_dict())
                print("Target net updated.")
            frames_seen+=1
            cumureward += reward
            cumureward2 += reward2
            avgrewards.append(np.sum(np.array(rewards))/episode)
            if frames_seen % 10000 == 0:
                actor.saveModel(y,'actor.pth')
                navigator.saveModel(y_navigator, 'navigato.pth')
            if done:
                games_played += 1
                total_kills += kills
                break
            
        print("kills",kills,
        "deaths", deaths,
        "Score:", cumureward,
        "score2:",cumureward2,
        " Episode:", episode,
         " frames_seen:", frames_seen , 
         " ACTOR_Epsilon:", actor.EPSILON,
          "NAVI_Epsilon", navigator.EPSILON,
           " episode_accuracy", correct/preds,
            "enemy_states", actor.ones/len(actor.replay_memory),
            "not_enemy_states", actor.zeros/len(actor.replay_memory))
        if len(actor.replay_memory) < hyperparameters.REPLAY_MEMORY_SIZE:
            print("replay_mem_size",len(actor.replay_memory))
        if pred_enemy > 0:
            print("epsisode_acc_enemy_in_frame_pred", pred_enemy_correct / pred_enemy)
        if pred_not_enemy > 0:
            print("epsisode_acc_enemy_not_in_frame_pred", pred_not_enemy_correct / pred_not_enemy)
        print("accuracy", accuracy)
        print("actor_loss",loss,"navi_loss", loss_navi)
        if loss is not None:
            wandb.log({"avg kills": total_kills/games_played,
            "kills": kills,"Reward per episode":cumureward, 
            "Loss":loss, 
            "training_accuracy": accuracy, 
            "navi loss": loss_navi, 
            " episode_accuracy": correct/preds, 
            "epsisode_acc_enemy_in_frame_pred": pred_enemy_correct / pred_enemy if pred_enemy > 0 else 0,
            "epsisode_acc_enemy_not_in_frame_pred": pred_not_enemy_correct / pred_not_enemy if pred_not_enemy > 0 else 0,
            "enemy_in_state_in_replay_memory": actor.ones/len(actor.replay_memory)})

if __name__ == "__main__":
    game = "VizdoomDeathmatch-v0"
    train(game)