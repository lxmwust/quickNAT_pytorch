"""
Data utility functions.
Sample command to create new dataset - python quickNat_pytorch/data_utils.py -dd /home/masterthesis/shayan/nas_drive/Data_Neuro/OASISchallenge/FS -ld /home/masterthesis/shayan/nas_drive/Data_Neuro/OASISchallenge -trv datasets/train_volumes.txt -tev datasets/test_volumes.txt -rc Neo -o COR -df datasets/coronal
"""

import os
import numpy as np
import torch
import torch.utils.data as data
import h5py
import argparse
import os
import nibabel as nb

class ImdbData(data.Dataset):
    def __init__(self, X, y, w):
        self.X = X if len(X.shape) == 4 else X[:,np.newaxis,:,:]
        self.y = y 
        self.w = w 

    def __getitem__(self, index):
        img = torch.from_numpy(self.X[index])
        label = torch.from_numpy(self.y[index])
        weight = torch.from_numpy(self.w[index])
        return img, label, weight

    def __len__(self):
        return len(self.y)
    
def get_data(data_params):
    Data_train = h5py.File(os.path.join(data_params['base_dir'], data_params['train_data_file'] ), 'r')
    Label_train = h5py.File(os.path.join(data_params['base_dir'], data_params['train_label_file'] ), 'r')
    Class_Weight_train = h5py.File(os.path.join(data_params['base_dir'], data_params['train_class_weights_file'] ), 'r')
    Weight_train = h5py.File(os.path.join(data_params['base_dir'], data_params['train_weights_file'] ), 'r')

    Data_test = h5py.File(os.path.join(data_params['base_dir'], data_params['test_data_file'] ), 'r')
    Label_test = h5py.File(os.path.join(data_params['base_dir'], data_params['test_label_file'] ), 'r')
    Class_Weight_test = h5py.File(os.path.join(data_params['base_dir'], data_params['test_class_weights_file'] ), 'r')
    Weight_test = h5py.File(os.path.join(data_params['base_dir'], data_params['test_weights_file'] ), 'r')
    
    return (ImdbData(Data_train['OASIS_data_train'][()], Label_train['OASIS_label_train'][()], Class_Weight_train['OASIS_class_weights_train'][()]),
            ImdbData(Data_test['OASIS_data_test'][()], Label_test['OASIS_label_test'][()], Class_Weight_test['OASIS_class_weights_test'][()]))
    

ORIENTATION = {
    'coronal': "COR",
    'axial': "AXI",
    'sagital': "SAG"
}

def _rotate_orientation(volume_data, volume_label, orientation=ORIENTATION['coronal']):
    if orientation == ORIENTATION['coronal']:
        return volume_data.transpose((2,0,1)), volume_label.transpose((2,0,1))
    elif orientation == ORIENTATION['axial']:
        return volume_data.transpose((1,2,0)), volume_label.transpose((1,2,0))        
    elif orientation == ORIENTATION['sagital']:
        return volume_data, volume_label
    else:
        raise ValueError("Invalid value for orientation. Pleas see help")
    
def _estimate_weights_mfb(labels):
    class_weights = np.zeros_like(labels)
    unique, counts = np.unique(labels, return_counts = True)
    median_freq = np.median(counts)
    weights = np.zeros(len(unique))
    for i, label in enumerate(unique):
        class_weights+= (median_freq // counts[i]) * np.array(labels == label)
        weights[int(label)] = median_freq // counts[i]
    
    grads = np.gradient(labels)
    edge_weights = (grads[0]**2 + grads[1]**2) > 0
    class_weights += 2 *  edge_weights
    return class_weights, weights
    
def _remap_labels(labels, remap_config):
    """
    Function to remap the label values into the desired range of algorithm
    """    
    if remap_config == 'FS':
        label_list = [2, 3, 4, 5, 7, 8, 10, 11, 12, 13, 14, 15, 16, 17, 18, 24, 26, 28, 41, 42, 43, 44, 46, 47, 49, 50, 51, 52, 53, 54, 58, 60]
    elif remap_config == 'Neo':
        labels[(labels>=100) & (labels % 2 == 0)] = 210
        labels[(labels>=100) & (labels % 2 == 1)] = 211            
        label_list = [45, 211, 52, 50, 41, 39, 60, 37, 58, 56, 4, 11, 35, 48, 32, 46, 30, 62, 44, 210, 51, 49, 40, 38, 59, 36, 57, 55, 47, 31, 23, 61]
    else:
        raise ValueError("Invalid argument value for remap config, only valid options are FS and Neo")

    new_labels = np.zeros_like(labels)
        
    for i, label in enumerate(label_list):
        label_present = np.zeros_like(labels)
        label_present[labels == label] = 1
        new_labels = new_labels + (i+1) * label_present
    
    return new_labels
        
def _select_slices(data, labels, skip_Frame = 40):
    """
    This function removes the useless black slices from the start and end. And then selects every even numbered frame.
    """
    no_slices, H, W = data.shape
    mask_vector = np.zeros(no_slices, dtype = int)
    mask_vector[::2], mask_vector[1::2] = 1, 0
    mask_vector[:skip_Frame], mask_vector[-skip_Frame:-1] = 0, 0

    data_reduced = np.compress(mask_vector, data, axis = 0).reshape(-1 , H, W)
    labels_reduced = np.compress(mask_vector, labels, axis = 0).reshape(-1 , H, W)    

    return data_reduced, labels_reduced


    
def _convertToHd5(data_dir, label_dir, volumes_txt_file , remap_config, orientation=ORIENTATION['coronal']):
    """
    
    """
    with open(volumes_txt_file) as file_handle:
        volumes_to_use = file_handle.read().splitlines()
    file_paths = [[os.path.join(data_dir, vol, 'mri/orig.mgz'), os.path.join(label_dir, vol+'_glm.mgz')] for vol in volumes_to_use]
    
    data_h5, label_h5, class_weights_h5, weights_h5 = [], [], [], []
    
    for file_path in file_paths:
        volume_data, volume_label = nb.load(file_path[0]).get_fdata(), nb.load(file_path[1]).get_fdata()
        volume_data, volume_label = _rotate_orientation(volume_data, volume_label, orientation)
        volume_data = (volume_data - np.min(volume_data)) / (np.max(volume_data) - np.min(volume_data))
        data, labels = _select_slices(volume_data, volume_label)
        labels = _remap_labels(labels, remap_config)
        class_weights, weights = _estimate_weights_mfb(labels)
        data_h5.append(data)
        label_h5.append(labels)
        class_weights_h5.append(class_weights)
        weights_h5.append(weights)
    no_slices, H, W = np.array(data_h5)[0].shape
    return np.array(data_h5).reshape((-1, H, W)), np.array(label_h5).reshape((-1, H, W)), np.array(class_weights_h5).reshape((-1, H, W)), np.array(weights_h5)
    

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument('--data_dir','-dd', required = True, help = 'Base directory of the data folder. This folder should contain one folder per volume, and each volumn folder should have an orig.mgz file')
    parser.add_argument('--label_dir', '-ld',required = True,  help = 'Base directory of all the label files. This folder should have one file per volumn with same name as the corresponding volumn folder name inside data_dir')
    parser.add_argument('--train_volumes', '-trv',required = True, help = 'Path to a text file containing the list of volumes to be used for training')
    parser.add_argument('--test_volumes', '-tev', required = True, help = 'Path to a text file containing the list of volumes to be used for testing')
    parser.add_argument('--remap_config', '-rc', required = True, help = 'Valid options are "FS" and "Neo"')
    parser.add_argument('--orientation', '-o', required = True, help = 'Valid options are COR, AXI, SAG')
    parser.add_argument('--destination_folder', '-df', help = 'Path where to generate the h5 files')
    
    args = parser.parse_args()
    data_train, label_train, class_weights_train, weights_train = _convertToHd5(args.data_dir, args.label_dir, args.train_volumes, args.remap_config, args.orientation)
    data_test, label_test, class_weights_test,  weights_test = _convertToHd5(args.data_dir, args.label_dir, args.test_volumes, args.remap_config, args.orientation)
        
    if args.destination_folder and not os.path.exists(args.destination_folder):
        os.makedirs(args.destination_folder)
        
    DESTINATION_FOLDER = args.destination_folder if args.destination_folder else ""
    
    DATA_TRAIN_FILE = os.path.join(DESTINATION_FOLDER, "Data_train.h5")
    LABEL_TRAIN_FILE = os.path.join(DESTINATION_FOLDER, "Label_train.h5")
    WEIGHTS_TRAIN_FILE = os.path.join(DESTINATION_FOLDER, "Weight_train.h5")
    CLASS_WEIGHTS_TRAIN_FILE = os.path.join(DESTINATION_FOLDER, "Class_Weight_train.h5")
    DATA_TEST_FILE = os.path.join(DESTINATION_FOLDER, "Data_test.h5")
    LABEL_TEST_FILE = os.path.join(DESTINATION_FOLDER, "Label_test.h5")
    WEIGHTS_TEST_FILE = os.path.join(DESTINATION_FOLDER, "Weight_test.h5")
    CLASS_WEIGHTS_TEST_FILE = os.path.join(DESTINATION_FOLDER, "Class_Weight_test.h5")
    
    with h5py.File(DATA_TRAIN_FILE,"w") as data_train_handle, h5py.File(LABEL_TRAIN_FILE,"w") as label_train_handle, h5py.File(WEIGHTS_TRAIN_FILE,"w") as weights_train_handle,h5py.File(CLASS_WEIGHTS_TRAIN_FILE,"w") as class_weights_train_handle, h5py.File(DATA_TEST_FILE,"w") as data_test_handle, h5py.File(LABEL_TEST_FILE,"w") as label_test_handle, h5py.File(WEIGHTS_TEST_FILE,"w") as weights_test_handle, h5py.File(CLASS_WEIGHTS_TEST_FILE,"w") as class_weights_test_handle:
        data_train_handle.create_dataset("OASIS_data_train", data = data_train)
        label_train_handle.create_dataset("OASIS_label_train", data = label_train)
        class_weights_train_handle.create_dataset("OASIS_class_weights_train", data = class_weights_train)
        weights_train_handle.create_dataset("OASIS_weights_train", data = weights_train)
        data_test_handle.create_dataset("OASIS_data_test", data = data_test)
        label_test_handle.create_dataset("OASIS_label_test", data = label_test)
        class_weights_test_handle.create_dataset("OASIS_class_weights_test", data = class_weights_test)
        weights_test_handle.create_dataset("OASIS_weights_test", data = weights_test)