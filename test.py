#coding=utf-8
import os
import json
import csv
import argparse
import pandas as pd
import numpy as np
from math import ceil
from tqdm import tqdm
import pickle
import shutil

import torch
import torch.nn as nn
from torch.autograd import Variable
from torch.nn import CrossEntropyLoss
from torchvision import datasets, models
import torch.backends.cudnn as cudnn
import torch.nn.functional as F
import matplotlib.pyplot as plt

from transforms import transforms
from models.LoadModel import MainModel
from utils.dataset_DCL import collate_fn4train, collate_fn4test, collate_fn4val, dataset
from config import LoadConfig, load_data_transformers
from utils.test_tool import set_text, save_multi_img, cls_base_acc

import pdb
import cv2

os.environ['CUDA_DEVICE_ORDRE'] = 'PCI_BUS_ID'
os.environ['CUDA_VISIBLE_DEVICES'] = '0,1,2,3'

def parse_args():
    parser = argparse.ArgumentParser(description='dcl parameters')
    parser.add_argument('--data', dest='dataset',
                        default='CUB', type=str)
    parser.add_argument('--backbone', dest='backbone',
                        default='resnet50', type=str)
    parser.add_argument('--b', dest='batch_size',
                        default=1, type=int)
    parser.add_argument('--nw', dest='num_workers',
                        default=1, type=int)
    parser.add_argument('--ver', dest='version',
                        default='val', type=str)
    parser.add_argument('--save', dest='resume',
                        default=None, type=str)
    parser.add_argument('--size', dest='resize_resolution',
                        default=512, type=int)
    parser.add_argument('--crop', dest='crop_resolution',
                        default=448, type=int)
    parser.add_argument('--ss', dest='save_suffix',
                        default=None, type=str)
    parser.add_argument('--acc_report', dest='acc_report',
                        action='store_true')
    parser.add_argument('--swap_num', default=[7, 7],
                    nargs=2, metavar=('swap1', 'swap2'),
                    type=int, help='specify a range')
    args = parser.parse_args()
    return args


def demo(sess, net, image_name):
    """Detect object classes in an image using pre-computed object proposals."""
 
    # Load the demo image
    im_file = os.path.join(cfg.DATA_DIR, 'demo', image_name)
    im = cv2.imread(im_file)
 
    # Detect all object classes and regress object bounds
    timer = Timer()
    timer.tic()
    scores, boxes = im_detect(sess, net, im)
    timer.toc()
    print('Detection took {:.3f}s for {:d} object proposals'.format(timer.total_time, boxes.shape[0]))
 
    # Visualize detections for each class


if __name__ == '__main__':
    args = parse_args()
    print(args)
    #if args.submit:
    if True:
        args.version = 'test'
        if args.save_suffix == '':
            raise Exception('**** miss --ss save suffix is needed. ')

    Config = LoadConfig(args, args.version)
    transformers = load_data_transformers(args.resize_resolution, args.crop_resolution, args.swap_num)
    data_set = dataset(Config,\
                       anno=Config.val_anno if args.version == 'val' else Config.test_anno ,\
                       #unswap=transformers["None"],\
                       swap=transformers["None"],\
                       totensor=transformers['test_totensor'],\
                       test=True)

    dataloader = torch.utils.data.DataLoader(data_set,\
                                             batch_size=args.batch_size,\
                                             shuffle=False,\
                                             num_workers=args.num_workers,\
                                             collate_fn=collate_fn4test)

    setattr(dataloader, 'total_item_len', len(data_set))

    cudnn.benchmark = True

    model = MainModel(Config)
    model_dict=model.state_dict()
    for k, v in model_dict.items():
        print(k)
    resume = './net_model/training_descibe_4158_CUB/weights_1_42854_0.7008_0.9519.pth'
    pretrained_dict=torch.load(resume)
    pretrained_dict = {k[7:]: v for k, v in pretrained_dict.items() if k[7:] in model_dict}
    for k, v in pretrained_dict.items():
        print(k)
    model_dict.update(pretrained_dict)
    #model.load_state_dict(pretrained_dict['net_state_dict'])
    #load_state_dict(ckpt['net_state_dict'])
    model.load_state_dict(model_dict)
    model.cuda()
    model = nn.DataParallel(model)

    model.train(False)
    with torch.no_grad():
        val_corrects1 = 0
        val_corrects2 = 0
        val_corrects3 = 0
        val_size = ceil(len(data_set) / dataloader.batch_size)
        result_gather = {}
        count_bar = tqdm(total=dataloader.__len__())
        for batch_cnt_val, data_val in enumerate(dataloader):
            count_bar.update(1)
            inputs, labels, img_name = data_val
            #print(img_name)
            #imggg = cv2.imread(img_name)
            #print(imggg)


            inputs = Variable(inputs.cuda())
            labels = Variable(torch.from_numpy(np.array(labels)).long().cuda())

            outputs = model(inputs)
            outputs_pred = outputs[0] + outputs[1][:,0:Config.numcls] + outputs[1][:,Config.numcls:2*Config.numcls]

            top3_val, top3_pos = torch.topk(outputs_pred, 3)
            #print(top3_val)  
            #tensor([[57.0976, 37.0089, 30.7548]], device='cuda:0')         
            #print(top3_pos[:, 0])            
            #tensor([477], device='cuda:0')
            #print(top3_pos[:, 1])
            #tensor([390], device='cuda:0')
            #print(top3_pos[:, 2])            
            #tensor([228], device='cuda:0')

            if args.version == 'val':
                #print(top3_val)
                #print(top3_pos[:, 0])
                batch_corrects1 = torch.sum((top3_pos[:, 0] == labels)).data.item()
                val_corrects1 += batch_corrects1
                batch_corrects2 = torch.sum((top3_pos[:, 1] == labels)).data.item()
                val_corrects2 += (batch_corrects2 + batch_corrects1)
                batch_corrects3 = torch.sum((top3_pos[:, 2] == labels)).data.item()
                val_corrects3 += (batch_corrects3 + batch_corrects2 + batch_corrects1)

            if args.acc_report:
                for sub_name, sub_cat, sub_val, sub_label in zip(img_name, top3_pos.tolist(), top3_val.tolist(), labels.tolist()):
                    result_gather[sub_name] = {'top1_cat': sub_cat[0], 'top2_cat': sub_cat[1], 'top3_cat': sub_cat[2],
                                               'top1_val': sub_val[0], 'top2_val': sub_val[1], 'top3_val': sub_val[2],
                                               'label': sub_label}
    if args.acc_report:
        torch.save(result_gather, 'result_gather_%s'%resume.split('/')[-1][:-4]+ '.pt')

    count_bar.close()

    if args.acc_report:

        val_acc1 = val_corrects1 / len(data_set)
        val_acc2 = val_corrects2 / len(data_set)
        val_acc3 = val_corrects3 / len(data_set)
        print('%sacc1 %f%s\n%sacc2 %f%s\n%sacc3 %f%s\n'%(8*'-', val_acc1, 8*'-', 8*'-', val_acc2, 8*'-', 8*'-',  val_acc3, 8*'-'))

        cls_top1, cls_top3, cls_count = cls_base_acc(result_gather)

        acc_report_io = open('acc_report_%s_%s.json'%(args.save_suffix, resume.split('/')[-1]), 'w')
        json.dump({'val_acc1':val_acc1,
                   'val_acc2':val_acc2,
                   'val_acc3':val_acc3,
                   'cls_top1':cls_top1,
                   'cls_top3':cls_top3,
                   'cls_count':cls_count}, acc_report_io)
        acc_report_io.close()

    im_names = ['test_image1.jpg', 'test_image1.jpg', 'test_image1.jpg']
    #for im_name in im_names:
    #    print('~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~')
    #    print('Demo for data/demo/{}'.format(im_name))
    #    #demo(sess, net, im_name)
    #plt.show()
    # 001_奥迪_奥迪_a1_2011 0
    #image_aa = cv2.imread('/media/zjkj/35196947-b671-441e-9631-6245942d671b/vehicle_type_v2d/vehicle_type_v2d/193_双龙大宇/柯兰多/unknown/KPTA0A18/KPTA0A18#KPTA0A18_闽F6915T_02_520000100529_520000104757104474.jpg', flags=1)
    #cv2.imshow('Example',image_aa)
    #cv2.waitKey(10000)
    # 读入图片
    src = cv2.imread('test_image1.jpg')
 
    # 调用cv.putText()添加文字
    text = "Your are so beautiful!"
    AddText = src.copy()
    cv2.putText(AddText, text, (200, 100), cv2.FONT_HERSHEY_COMPLEX, 2.0, (100, 200, 200), 5)
 
    # 将原图片和添加文字后的图片拼接起来
    res = np.hstack([src, AddText])
 
    # 显示拼接后的图片
    cv2.imshow('text', res)
    cv2.waitKey()
    cv2.destroyAllWindows()


'''
/media/zjkj/35196947-b671-441e-9631-6245942d671b/vehicle_type_v2d/vehicle_type_v2d/193_双龙大宇/柯兰多/unknown/KPTA0A18/KPTA0A18#KPTA0A18_闽F6915T_02_520000100529_520000104757104474.jpg
'/media/zjkj/35196947-b671-441e-9631-6245942d671b/vehicle_type_v2d/vehicle_type_v2d/193_双龙大宇/柯兰多/unknown/KPTA0A18/KPTA0A18#KPTA0A18_闽F6915T_02_520000100529_520000104757104474.jpg']

tensor([[57.0976, 37.0090, 30.7548]], device='cuda:0')
tensor([477], device='cuda:0')

'''

