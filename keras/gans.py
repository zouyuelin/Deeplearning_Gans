# -*- coding: utf-8 -*-
'''
    @author:zyl
    author is zouyuelin
    a Master of
    Tianjin University(TJU),
    school of the Mechanical engineering
'''

import tensorflow as tf
from tensorflow import keras
#tf.enable_eager_execution()
import numpy as np
from PIL import Image
import os
import cv2
import time

batch_size = 4
epochs = 4
num_steps = 2000
coding_size = 30
tfrecords_path = 'data/train.tfrecords'

#--------------------------------------datasetTfrecord----------------   
def load_image(serialized_example):   
    features={
        'label': tf.io.FixedLenFeature([], tf.int64),
        'img_raw' : tf.io.FixedLenFeature([], tf.string)}
    parsed_example = tf.io.parse_example(serialized_example,features)
    image = tf.decode_raw(parsed_example['img_raw'],tf.uint8)
    image = tf.reshape(image,[-1,224,224,3])
    image = tf.cast(image,tf.float32)*(1./255)
    label = tf.cast(parsed_example['label'], tf.int32)
    label = tf.reshape(label,[-1,1])
    return image,label
 
def dataset_tfrecords(tfrecords_path,use_keras_fit=True): 
    #是否使用tf.keras
    if use_keras_fit:
        epochs_data = 1
    else:
        epochs_data = epochs
    dataset = tf.data.TFRecordDataset([tfrecords_path])#这个可以有多个组成[tfrecords_name1,tfrecords_name2,...],可以用os.listdir(tfrecords_path):
    dataset = dataset.repeat(epochs_data).batch(batch_size).map(load_image,num_parallel_calls = 2).shuffle(1000)

    iter = dataset.make_one_shot_iterator()#make_initialization_iterator
    train_datas = iter.get_next() #用train_datas[0],[1]的方式得到值
    return train_datas,iter

#------------------------------------tf.TFRecordReader-----------------
def read_and_decode(tfrecords_path):
    #根据文件名生成一个队列
    filename_queue = tf.train.string_input_producer([tfrecords_path],shuffle=True) 
    reader = tf.TFRecordReader()
    _,  serialized_example = reader.read(filename_queue)
    features = tf.parse_single_example(serialized_example,features={
        'label': tf.FixedLenFeature([], tf.int64),
        'img_raw' : tf.FixedLenFeature([], tf.string),})

    image = tf.decode_raw(features['img_raw'], tf.uint8)
    image = tf.reshape(image,[224,224,3])#reshape 200*200*3
    image = tf.cast(image,tf.float32)*(1./255)#image张量可以除以255，*(1./255)
    label = tf.cast(features['label'], tf.int32)
    img_batch, label_batch = tf.train.shuffle_batch([image,label],
                    batch_size=batch_size,
                    num_threads=4,
                    capacity= 640,
                    min_after_dequeue=5)
    return [img_batch,label_batch]

#Autodecode 解码器
def autoencode():
        encoder = keras.models.Sequential([
            keras.layers.Conv2D(32,kernel_size=3,padding='same',strides=2,activation='selu',input_shape=[224,224,3]),
            #112*112*32
            keras.layers.MaxPool2D(pool_size=2),
            #56*56*32
            keras.layers.Conv2D(64,kernel_size=3,padding='same',strides=2,activation='selu'),
            #28*28*64
            keras.layers.MaxPool2D(pool_size=2),
            #14*14*64
            keras.layers.Conv2D(128,kernel_size=3,padding='same',strides=2,activation='selu'),
            #7*7*128
            #反卷积
            keras.layers.Conv2DTranspose(128,kernel_size=3,strides=2,padding='same',activation='selu'),
            #14*14*128
            keras.layers.Conv2DTranspose(64,kernel_size=3,strides=2,padding='same',activation='selu'),
            #28*28*64
            keras.layers.Conv2DTranspose(32,kernel_size=3,strides=2,padding='same',activation='selu'),
            #56*56*32
            keras.layers.Conv2DTranspose(16,kernel_size=3,strides=2,padding='same',activation='selu'),
            #112*112*16
            keras.layers.Conv2DTranspose(3,kernel_size=3,strides=2,padding='same',activation='tanh'),#使用tanh代替sigmoid
            #224*224*3
            keras.layers.Reshape([224,224,3])
            ])
        return encoder

#train the gan
def train_gan(gan,train_datas,batch_size,num_steps=1000):
    generator,discriminator = gan.layers
    for step in range(num_steps):
        #get the time
        start_time = time.time()
        #phase 1 - training the discriminator
        noise = tf.random.normal(shape=[batch_size,coding_size])
        generated_images = generator(noise)
        x_fake_and_real = tf.concat([generated_images,train_datas[0]],axis=0)
        y1 = tf.constant([[0.]]*batch_size+[[1.]]*batch_size)
        discriminator.trainable = True
        dis_loss = discriminator.train_on_batch(x_fake_and_real,y1)
        
        #将keras 的train_on_batch函数放在gan网络中是明智之举
        #phase 2 - training the generator
        noise = tf.random.normal(shape=[batch_size,coding_size])
        y2 = tf.constant([[1.]]*batch_size)
        discriminator.trainable = False
        ad_loss = gan.train_on_batch(noise,y2)
        duration = time.time()-start_time
        if step % 5 == 0:
            #gan.save_weights('gan.h5')
            print("The step is %d,discriminator loss:%.3f,adversarial loss:%.3f"%(step,dis_loss,ad_loss),end=' ')
            print('%.2f s/step'%(duration))
        if step % 30 == 0 and step != 0:
            

def training_keras():
    '''
        卷积和池化输出公式：
            output_size = (input_size-kernel_size+2*padding)/strides+1
            
        keras的反卷积输出计算，一般不用out_padding
        1.若padding = 'valid':
            output_size = (input_size - 1)*strides + kernel_size
        2.若padding = 'same:
            output_size = input_size * strides
    '''
    generator = keras.models.Sequential([
            #fullyconnected nets
            keras.layers.Dense(256,activation='selu',input_shape=[coding_size]),
            keras.layers.Dense(64,activation='selu'),
            keras.layers.Dense(256,activation='selu'),
            keras.layers.Dense(1024,activation='selu'),
            keras.layers.Dense(7*7*64,activation='selu'),
            keras.layers.Reshape([7,7,64]),
            #7*7*64
            #反卷积
            keras.layers.Conv2DTranspose(64,kernel_size=3,strides=2,padding='same',activation='selu'),
            #14*14*64
            keras.layers.Conv2DTranspose(64,kernel_size=3,strides=2,padding='same',activation='selu'),
            #28*28*64
            keras.layers.Conv2DTranspose(32,kernel_size=3,strides=2,padding='same',activation='selu'),
            #56*56*32
            keras.layers.Conv2DTranspose(16,kernel_size=3,strides=2,padding='same',activation='selu'),
            #112*112*16
            keras.layers.Conv2DTranspose(3,kernel_size=3,strides=2,padding='same',activation='tanh'),#使用tanh代替sigmoid
            #224*224*3
            keras.layers.Reshape([224,224,3])
            ])
            
    discriminator = keras.models.Sequential([
            keras.layers.Conv2D(128,kernel_size=3,padding='same',strides=2,activation='selu',input_shape=[224,224,3]),
            keras.layers.MaxPool2D(pool_size=2),
            #56*56*128
            keras.layers.Conv2D(64,kernel_size=3,padding='same',strides=2,activation='selu'),
            keras.layers.MaxPool2D(pool_size=2),
            #14*14*64
            keras.layers.Conv2D(32,kernel_size=3,padding='same',strides=2,activation='selu'),
            #7*7*32
            keras.layers.Flatten(),
            #dropout 0.4
            keras.layers.Dropout(0.4),
            keras.layers.Dense(512,activation='selu'),
            keras.layers.Dropout(0.4),
            keras.layers.Dense(64,activation='selu'),
            keras.layers.Dropout(0.4),
            #the last net
            keras.layers.Dense(1,activation='sigmoid')
            ])
    #gans network        
    gan = keras.models.Sequential([generator,discriminator])
    
    #compile the net
    discriminator.compile(loss="binary_crossentropy",optimizer='rmsprop')# metrics=['accuracy'])
    discriminator.trainable=False
    gan.compile(loss="binary_crossentropy",optimizer='rmsprop')# metrics=['accuracy'])
    
    #dataset
    #train_datas = read_and_decode(tfrecords_path)
    train_datas,iter = dataset_tfrecords(tfrecords_path,use_keras_fit=False)
    
    #sess = tf.Session()
    #sess.run(iter.initializer)
    train_gan(gan=gan,
                train_datas=train_datas,
                batch_size=batch_size,
                num_steps=num_steps)
    
    #save the models 
    model_vision = '0001'
    model_name = 'gans'
    model_path = os.path.join(model_name,model_name)
    tf.saved_model.save(gan,model_path)
    
def main():
    training_keras()
main()
