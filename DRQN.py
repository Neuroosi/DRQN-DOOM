from hyperparameters import BATCH_SIZE
import torch
from torch import nn
from torch._C import device
from torch import optim
import random
import numpy as np
from collections import deque

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using {device} device")


class DRQN(nn.Module):

    def __init__(self, replay_memory_size = 2*10**5, batch_size = 32, gamma = 0.99, epsilon = 1, epsilon_min = 0.1,  epsilon_decay = 250000):
        self.replay_memory = deque(maxlen=replay_memory_size)
        self.ddqn = False
        self.REPLAY_MEMORY_SIZE = replay_memory_size
        self.BATCH_SIZE = batch_size
        self.GAMMA = gamma
        self.EPSILON = epsilon
        self.EPSILON_MIN = epsilon_min
        self.EPSILON_DECAY = (self.EPSILON-self.EPSILON_MIN)/epsilon_decay
        self.ones = 0
        self.zeros = 0

    def update_replay_memory(self, transition):
        if len(self.replay_memory) < self.REPLAY_MEMORY_SIZE:
            self.replay_memory.append(transition)
        else:
            first_element = self.replay_memory[0][5]
            if first_element == 1.0:
                self.ones -= 1
            else:
                self.zeros -= 1
            self.replay_memory.append(transition)
        if transition[5] == 1.0:
            self.ones += 1
        else:
            self.zeros += 1

    def train(self, agent, target, loss_fn, loss_fn_detector, optimizer):
        batch = random.sample(self.replay_memory, self.BATCH_SIZE)
        Y = []
        states = [torch.from_numpy(np.array(transition[0])/255) for transition in batch]
        states = torch.stack(states)
        states = states.float()
        states = torch.unsqueeze(states,axis = 1)
        next_states = [torch.from_numpy(np.array(transition[3])/255) for transition in batch]
        next_states = torch.stack(next_states)
        next_states = next_states.float()
        next_states = torch.unsqueeze(next_states,axis = 1)
        labels = [torch.from_numpy(np.array(transition[5])) for transition in batch]
        labels = torch.stack(labels)
        labels = labels.float()
        labels = labels.to(device)
        pred_output = agent.forward2(states)
        pred_output_p = agent.sigmoid(pred_output)
        pred_labels = (pred_output_p > 0.5).float()
        pred_labels = torch.squeeze(pred_labels,axis = 1)
        correct = torch.sum(torch.eq(pred_labels, labels))
        loss_det = loss_fn_detector( pred_output,torch.unsqueeze(labels, axis = 1))
        optimizer.zero_grad()
        h_target = torch.zeros([1,BATCH_SIZE,  512])
        c_target = torch.zeros([1,BATCH_SIZE,  512])
        h = torch.zeros([1, BATCH_SIZE, 512])
        c = torch.zeros([1, BATCH_SIZE, 512])
        y, y_hidden, y_cell = agent(states, h, c)
        target_y, target_y_hidden, target_y_cell= target(next_states, h_target, c_target)
        y = torch.squeeze(y, axis=0)
        target_y = torch.squeeze(target_y, axis = 0)
        #y_next = agent(next_states)
        for i,(state, action, reward, next_state, done, enemy) in enumerate(batch):
            if done:
                y[i][action] = reward
            elif self.ddqn is False:
                y[i][action] = reward + self.GAMMA*torch.max(target_y[i])
            else:
                y[i][action] = reward + self.GAMMA*target_y[i][torch.argmax(y_next[i])]
            Y.append(y[i])
        Y = torch.stack(Y)
        agent.train()
        h = torch.zeros([1,BATCH_SIZE,  512])
        c = torch.zeros([1,BATCH_SIZE,  512])
        pred, pred_hidden, pred_cell = agent(states,h , c)
        pred= torch.squeeze(pred, axis=0)
        loss = loss_fn(pred, Y) + loss_det
        loss.backward()
        for param in agent.parameters():
            param.grad.data.clamp_(-1, 1)
        optimizer.step()
        self.EPSILON = max(self.EPSILON_MIN, self.EPSILON-self.EPSILON_DECAY)
        return loss.item(), correct*1.0 / BATCH_SIZE


    def getPrediction(self, state, model, h, c):
        if np.random.rand() > self.EPSILON:
            with torch.no_grad():
                state = np.expand_dims(state, axis=0)
                state = torch.from_numpy(state)
                state = state.float()
                state = torch.unsqueeze(state,axis = 0)
                output, hidden, cell = model(state, h , c)
                return torch.argmax(output).item(), hidden, cell
        return random.randrange(model.actionSpaceSize), h, c

    def saveModel(self, agent, filename):
        torch.save(agent.state_dict(), filename)
        print("Model saved!")
    def loadModel(self, agent, filename):
        agent.load_state_dict(torch.load(filename))
        print("Model loaded!")