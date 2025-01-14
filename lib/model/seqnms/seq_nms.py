# --------------------------------------------------------
# Flow-Guided Feature Aggregation
# Copyright (c) 2016 by Contributors
# Copyright (c) 2017 Microsoft
# Licensed under The Apache-2.0 License [see LICENSE for details]
# Modified by Yuqing Zhu, Xizhou Zhu
# --------------------------------------------------------


import numpy as np

import profile
import cv2
import time
import copy
import pickle
import os
import copy
import pdb

#CLASSES = ('__background__',
#           'airplane', 'antelope', 'bear', 'bicycle', 'bird', 'bus',
#           'car', 'cattle', 'dog', 'domestic cat', 'elephant', 'fox',
#           'giant panda', 'hamster', 'horse', 'lion', 'lizard', 'monkey',
#           'motorcycle', 'rabbit', 'red panda', 'sheep', 'snake', 'squirrel',
#           'tiger', 'train', 'turtle', 'watercraft', 'whale', 'zebra')

CLASSES = ['bacon', 'bean', 'beef', 'blender', 'bowl', 'bread', 'butter', 'cabbage', 'carrot', 'celery', 'cheese', 'chicken', 'chickpea', 'corn', 'cream', 'cucumber', 'cup', 'dough', 'egg', 'flour', 'garlic', 'ginger', 'it', 'leaf', 'lemon', 'lettuce', 'lid', 'meat', 'milk', 'mixture', 'mushroom', 'mussel', 'mustard', 'noodle', 'oil', 'onion', 'oven', 'pan', 'paper', 'pasta', 'pepper', 'plate', 'pork', 'pot', 'potato', 'powder', 'processor', 'rice', 'salad', 'salt', 'sauce', 'seaweed', 'sesame', 'shrimp', 'soup', 'squid', 'sugar', 'that', 'them', 'they', 'tofu', 'tomato', 'vinegar', 'water', 'whisk', 'wine', 'wok']
           
NMS_THRESH = 0.3
IOU_THRESH = 0.5
MAX_THRESH=1e-2

box_dim = 0

def createLinks(dets_all):
    global box_dim
    # dets_all (cls_ind, frm_ind, box_ind, 5)
    links_all = []

    frame_num = len(dets_all[0])
    cls_num = len(CLASSES) - 1
    for cls_ind in range(cls_num):
        links_cls = []
        for frame_ind in range(frame_num - 1):
            dets1 = dets_all[cls_ind][frame_ind]
            dets2 = dets_all[cls_ind][frame_ind + 1]
            box1_num = len(dets1)
            box2_num = len(dets2)
            # get box_dim, may be 5 or 6
            if box_dim == 0 and box1_num > 0:
                box_dim = len(dets1[0])
            if not dets2.any():
                pass
            
            if frame_ind == 0:
                areas1 = np.empty(box1_num)
                for box1_ind, box1 in enumerate(dets1):
                    areas1[box1_ind] = (box1[2] - box1[0] + 1) * (box1[3] - box1[1] + 1)
            else:
                areas1 = areas2

            areas2 = np.empty(box2_num)
            for box2_ind, box2 in enumerate(dets2):
                areas2[box2_ind] = (box2[2] - box2[0] + 1) * (box2[3] - box2[1] + 1)

            links_frame = []

            for box1_ind, box1 in enumerate(dets1):
                if not dets2.any():
                    links_frame.append([])
                else:
                    area1 = areas1[box1_ind]
                    x1 = np.maximum(box1[0], dets2[:, 0])
                    y1 = np.maximum(box1[1], dets2[:, 1])
                    x2 = np.minimum(box1[2], dets2[:, 2])
                    y2 = np.minimum(box1[3], dets2[:, 3])
                    w = np.maximum(0.0, x2 - x1 + 1)
                    h = np.maximum(0.0, y2 - y1 + 1)
                    inter = w * h
                    ovrs = inter / (area1 + areas2 - inter)
                    links_box = [ovr_ind for ovr_ind, ovr in enumerate(ovrs) if
                                 ovr >= IOU_THRESH]
                    links_frame.append(links_box)
            links_cls.append(links_frame)
        # all links for each class are indicated, stored as box index in the next det
        links_all.append(links_cls)
    return links_all


def maxPath(dets_all, links_all):

    for cls_ind, links_cls in enumerate(links_all):

        delete_sets=[[]for i in range(0,len(dets_all[0]))]
        delete_single_box=[]
        dets_cls = dets_all[cls_ind]

        num_path=0
        # compute the number of links
        sum_links=0
        for frame_ind, frame in enumerate(links_cls):
            for box_ind,box in enumerate(frame):
                sum_links+=len(box)

        while True:

            num_path+=1

            rootindex, maxpath, maxsum = findMaxPath(links_cls, dets_cls,delete_single_box)

            if (maxsum<MAX_THRESH or sum_links==0 or len(maxpath) <1):
                break
            if (len(maxpath)==1):
                delete=[rootindex,maxpath[0]]
                delete_single_box.append(delete)
            rescore(dets_cls, rootindex, maxpath, maxsum)

            delete_set, num_delete=deleteLink(dets_cls, links_cls, rootindex, maxpath, NMS_THRESH)
            sum_links-=num_delete
            for i, box_ind in enumerate(maxpath):
                delete_set[i].remove(box_ind)
                delete_single_box.append([[rootindex+i],box_ind])
                for j in delete_set[i]:
                    dets_cls[i+rootindex][j]=np.zeros(box_dim)
                delete_sets[i+rootindex]=delete_sets[i+rootindex]+delete_set[i]

        for frame_idx,frame in enumerate(dets_all[cls_ind]):
            a=range(0,len(frame))
            keep=list(set(a).difference(set(delete_sets[frame_idx])))
            dets_all[cls_ind][frame_idx]=frame[keep,:]


    return dets_all

def getTube(dets_all, links_all):

    # init tube link
    # tbs_all: store tubes for all classes
    cls_num = len(CLASSES)
    tbs_all = [[] for i in range(cls_num)]
    for cls_ind, links_cls in enumerate(links_all):

        delete_sets=[[]for i in range(0,len(dets_all[0]))]
        delete_single_box=[]
        dets_cls = dets_all[cls_ind]

        num_path=0
        # compute the number of links
        sum_links=0
        for frame_ind, frame in enumerate(links_cls):
            for box_ind,box in enumerate(frame):
                sum_links+=len(box)
        # tbs_cls: tubes for each class, each tube in form of (root_index, maxpath)
        tbs_cls = []
        while True:

            num_path+=1

            rootindex, maxpath, maxsum = findMaxPath(links_cls, dets_cls,delete_single_box)
            tbs_cls.append((rootindex, maxpath, maxsum))

            if (maxsum<MAX_THRESH or sum_links==0 or len(maxpath) <1):
                break
            if (len(maxpath)==1):
                delete=[rootindex,maxpath[0]]
                delete_single_box.append(delete)
            rescore(dets_cls, rootindex, maxpath, maxsum)
            delete_set, num_delete=deleteLink(dets_cls, links_cls, rootindex, maxpath, NMS_THRESH)
            sum_links -= num_delete
            for i, box_ind in enumerate(maxpath):
                delete_set[i].remove(box_ind)
                delete_single_box.append([[rootindex+i],box_ind])
                for j in delete_set[i]:
                    dets_cls[i+rootindex][j]=np.zeros(box_dim)
                delete_sets[i+rootindex] = delete_sets[i+rootindex]+delete_set[i]
        dets_all_pure = copy.deepcopy(dets_all)
        for frame_idx,frame in enumerate(dets_all_pure[cls_ind]):
            if not frame.any():
                continue
            a=range(0,len(frame))
            keep=list(set(a).difference(set(delete_sets[frame_idx])))
            try:
                dets_all_pure[cls_ind][frame_idx]=frame[keep,:]
            except:
                pdb.set_trace()
        tbs_all[cls_ind] = tbs_cls
    return dets_all, dets_all_pure, tbs_all

def findMaxPath(links, dets, delete_single_box):
    """
    :return rootindex: the frame index that the link begin
    :return maxpath: the list that contain box id
    """

    len_dets=[len(dets[i]) for i in range(len(dets))]
    max_boxes=np.max(len_dets)
    num_frame=len(links)+1
    # a: store score of each box in one class
    a=np.zeros([num_frame,max_boxes])
    new_dets=np.zeros([num_frame,max_boxes])
    for delete_box in delete_single_box:
        new_dets[delete_box[0],delete_box[1]]=1
    if(max_boxes==0):
        max_path=[]
        return 0,max_path,0
    # b: store the box id
    b=np.full((num_frame,max_boxes),-1)
    for l in range(len(dets)):
        for j in range(len(dets[l])):
            if(new_dets[l,j]==0):
                a[l,j]=dets[l][j][4]

    for i in range(1,num_frame):
        l1=i-1;
        for box_id,box in enumerate(links[l1]):
            for next_box_id in box:
                weight_new=a[i-1,box_id]+dets[i][next_box_id][4]
                # find the next linked box with maximum confidence (if add flow, add here, select with flow regularization)
                if(weight_new>a[i,next_box_id]):
                    a[i,next_box_id]=weight_new
                    b[i,next_box_id]=box_id

    i,j=np.unravel_index(a.argmax(),a.shape)

    maxpath=[j]
    maxscore=a[i,j]
    while(b[i,j]!=-1):
        maxpath.append(b[i,j])
        j=b[i,j]
        i=i-1
    rootindex=i
    maxpath.reverse()
    return rootindex, maxpath, maxscore


def rescore(dets, rootindex, maxpath, maxsum):
    newscore = maxsum / len(maxpath)

    for i, box_ind in enumerate(maxpath):
        dets[rootindex + i][box_ind][4] = newscore


def deleteLink(dets, links, rootindex, maxpath, thesh):

    delete_set=[]
    num_delete_links=0

    for i, box_ind in enumerate(maxpath):
        areas = [(box[2] - box[0] + 1) * (box[3] - box[1] + 1) for box in dets[rootindex + i]]
        area1 = areas[box_ind]
        box1 = dets[rootindex + i][box_ind]
        x1 = np.maximum(box1[0], dets[rootindex + i][:, 0])
        y1 = np.maximum(box1[1], dets[rootindex + i][:, 1])
        x2 = np.minimum(box1[2], dets[rootindex + i][:, 2])
        y2 = np.minimum(box1[3], dets[rootindex + i][:, 3])
        w = np.maximum(0.0, x2 - x1 + 1)
        h = np.maximum(0.0, y2 - y1 + 1)
        inter = w * h

        ovrs = inter / (area1 + areas - inter)
        #saving the box need to delete
        deletes = [ovr_ind for ovr_ind, ovr in enumerate(ovrs) if ovr >= 0.3]
        delete_set.append(deletes)

        #delete the links except for the last frame
        if rootindex + i < len(links):
            for delete_ind in deletes:
                num_delete_links+=len(links[rootindex+i][delete_ind])
                links[rootindex + i][delete_ind] = []

        if i > 0 or rootindex > 0:

            #delete the links which point to box_ind
            for priorbox in links[rootindex + i - 1]:
                for delete_ind in deletes:
                    if delete_ind in priorbox:
                        priorbox.remove(delete_ind)
                        num_delete_links+=1

    return delete_set, num_delete_links

def seq_nms(dets):
    links = createLinks(dets)
    dets, dets_pure, tbs = getTube(dets, links)
    return dets, dets_pure, tbs 
    
#def seq_nms(dets):
#    links = createLinks(dets)
#    dets, tbs=getTube(dets, links)
#    return dets, tbs 

