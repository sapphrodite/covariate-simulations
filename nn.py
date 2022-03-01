from simulator import fitting, common
import nn_common

import numpy as np
import torch
from torch.autograd import Variable 
import matplotlib.pyplot as plt
import sys, os, itertools
	
# Definition of the training network
class ANN(torch.nn.Module):
    def __init__(self, input_dim, output_dim):
        loss_fn = None
        optimizer = None
        super(ANN, self).__init__()
        self.fc1 = torch.nn.Linear(input_dim, input_dim*2)
        self.fc2 = torch.nn.Linear(input_dim*2, input_dim*3)
        self.fc3 = torch.nn.Linear(input_dim*3, input_dim*4)
        self.fc4 = torch.nn.Linear(input_dim*4, input_dim*5)
        self.fc5 = torch.nn.Linear(input_dim*5, input_dim*4)
        self.fc6 = torch.nn.Linear(input_dim*4, input_dim*2)
        self.output_layer = torch.nn.Linear(input_dim*2, output_dim)
        self.dropout = torch.nn.Dropout(0.3)

    def swish(self, x):
      return x * torch.sigmoid(x)

    def forward(self, x):
        x = self.swish(self.fc1(x))
        x = self.dropout(x)
        x = self.swish(self.fc2(x))
        x = self.dropout(x)
        x = self.swish(self.fc3(x))
        x = self.dropout(x)
        x = self.swish(self.fc4(x))
        x = self.dropout(x)
        x = self.swish(self.fc5(x))
        x = self.dropout(x)
        x = self.swish(self.fc6(x))
        x = self.dropout(x)
        x = self.output_layer(x)
        return x
        


def training_epoch(nn, train_loader):
    train_loss = 0.0
    cov_count = 0
    for data, target in train_loader:
        sorted_results = nn_common.sortHazard(target)
        data = Variable(data).float()
        target = Variable(target).type(torch.FloatTensor)
        # Transfer Data to GPU if available
        if torch.cuda.is_available():
            data, target = data.cuda(), target.cuda()

        # Clear the gradients
        nn.optimizer.zero_grad()
        # Forward Pass
        output = nn(data)
        sorted_output = nn_common.sortHazard(output)
        # Find the Loss
        loss = nn.loss_fn(output, target)
        # Calculate gradients
        loss.backward()
        # Update Weights
        nn.optimizer.step()
        # Calculate Loss
        train_loss += loss.item()
        print(f"[+] covariate vector: {bin(cov_count)} [+]")
        print(f"[+] Sorted output for results: {sorted_results} [+]")
        print(f"[+] Sorted output for model prediction {sorted_output} [+] \n")
        cov_count += 1
    return train_loss / (cov_count + 1)  # (cov count + 1) gives number of iterations taken, to average
  
def validation_epoch(nn, valid_loader, accumulators, location):
    valid_loss = 0.0
    cov_count = 0
    for data, target in valid_loader:
        data = Variable(data).float()
        target = Variable(target).type(torch.FloatTensor)
        # Transfer Data to GPU if available
        if torch.cuda.is_available():
            data, target = data.cuda(), target.cuda()

        # Forward Pass
        output = nn(data)
        # uses dictionary to sort the models output/ for validation. Same process can be done for training but that is not really interesting.
        numerical_results = nn_common.sortHazard(target)
        model_results = nn_common.sortHazard(output)

        for i, hazard in enumerate(model_results):
            if hazard[0] == numerical_results[0][0]: # fuck tuples
                location[i] += 1

        print(f"!! covariate vector: {bin(cov_count)} !!\n[+] Numerical results: {numerical_results}\n[+] or model results {model_results}\n")
        cov_count += 1
        # Find the Loss
        loss = nn.loss_fn(output, target)
        # Calculate Loss
        valid_loss += loss.item()
    return (valid_loss / (cov_count + 1)) # (cov count + 1) gives number of iterations taken, to average

        
def moving_average(x, w):
    return np.convolve(x, np.ones(w), 'valid') / w

def train_model(num_hazards, num_covariates, num_intervals, learning_rate, weight_decay, output_directory):
    epochs = 150
    nn = ANN(num_intervals*(num_covariates+1),num_hazards)
    nn.loss_fn = torch.nn.L1Loss()
    nn.optimizer = torch.optim.Adam(nn.parameters(), lr=learning_rate, weight_decay=weight_decay)
    if torch.cuda.is_available():
        nn.cuda() 
  
    loss_array = [0] * int(epochs)
    for e in range(epochs):
        train_loader = nn_common.gen_training_detaset(e, num_hazards, num_covariates, num_intervals, False)
        train_loss = training_epoch(nn, train_loader)
        loss_array.append(train_loss)
        print(f'- ---Epoch {e+1} \t\t Average Training Loss: {train_loss}\n')

    print("\n-------------------- VALIDATION LOOP -----------------------\n")

    accumulators = {}
    for index, m in enumerate(common.models[:num_hazards]):
        accumulators[m] = []
    min_valid_loss = np.inf
    val_array = [0] * int(epochs) 
    location = [0]*num_hazards
    with torch.no_grad():
        nn.eval()
        for i in range(epochs):
            valid_loader = nn_common.gen_training_detaset(i, num_hazards, num_covariates, num_intervals, True)
            valid_loss = validation_epoch(nn, valid_loader, accumulators, location)
            val_array.append(valid_loss)
            print(f'----Epoch {i+1} Average Validation Loss: {valid_loss}\n')
            if min_valid_loss > valid_loss:
                print(f'------Validation Loss Decreased({min_valid_loss:.3f}--->{valid_loss:.3f}) \t Saving The Model------\n')
                min_valid_loss = valid_loss
                # Saving State Dict
                torch.save(nn.state_dict(), 'saved_model.pth')

    train_avg = moving_average(loss_array, 2)  
    val_avg = moving_average(val_array, 2)
    fig = plt.figure(figsize=(12, 6))
    ax = fig.add_subplot(121)
    ax2 = fig.add_subplot(122)
    ax.set_title('Training Loss vs Epoch')
    ax.plot(train_avg, color="red")
    #ax.savefig(f"TrainingLossvsEpoch.png")    #Can be consolidated by using a function, maybe called graphResults(loss_array, val_array).
    ax2.set_title('Validation Loss vs Epoch')
    ax2.plot(val_avg, color="red")
    #ax2.savefig(f"ValidationLossvsEpoch.png")
    total_chances = epochs * 2**num_covariates
    plt.savefig(f"{output_directory}/ValandTrain.png")
    plt.close()


    # plt.close()
    # for model in common.models[:num_hazards]:
    #     plt.title(f"{model} - Amount and Locations of Accurate Prediction")
    #     plt.hist(accumulators[model], edgecolor='black')
    #     plt.plot()
    #     plt.savefig(f"{output_directory}/{model} - Amount and Locations of Accurate Prediction")
    #     plt.close()

    plt.title("Model Predictions")
    plt.ylabel('Number of Accurate Classifications')
    plt.bar(("1st","2nd", "3rd"), location , edgecolor = 'black')
    plt.plot()
    plt.savefig('CumulativeModelAccuracy')
    plt.close()
    
    for model in common.models[:num_hazards]:
        print(f"{model} accuracy: {len(accumulators[model])/epochs}\n")
    print(f"The location of the correct placements is {location}")



#(num_hazards , num_covariates , num_intervals , learning_rate , weight_decay , output_directory)
train_model(3, 1, 50, 0.0005, 1e-7,"sim1")
