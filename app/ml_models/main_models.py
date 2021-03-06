from pprint import pprint
import os

import tensorflow as tf
import json # for saving vocabulary dictionaries
# import tensorflow_copy as tf


# import read_data
# import read_data_amazon
import read_data
from models.n2n_DMN.dmn import n2nModel
from app.ml_models.read_data import DataSet

# this will help with the database connection (pretty sure lol)
# from app.database import db_session
# from app.models import User, Story, n2nModel

flags = tf.app.flags

# File directories
flags.DEFINE_string("log_dir", "log", "Log directory [log]")
flags.DEFINE_string("data_dir", 'data/babi/en/', "Data folder directory [data/babi/en]")
flags.DEFINE_string("amazon_data_dir", 'data/amazon/', "Amazon data folder [data/amazon/]")
flags.DEFINE_string("cust_data_dir", 'data/custom/','Custom data folder [data/custom]')
flags.DEFINE_string("save_dir", "save", "Save path [save]")

# Common training parameters
flags.DEFINE_integer("batch_size", 1, "Batch size during training and testing [32]")
flags.DEFINE_float("init_mean", 0, "Initial weight mean [0]")
flags.DEFINE_float("init_std", 0.1, "Initial weight std [0.1]")
flags.DEFINE_float("init_lr", 0.01, "Initial learning rate [0.01]")
flags.DEFINE_integer("num_epochs", 1, "Total number of epochs for training [100]")
flags.DEFINE_float("anneal_ratio", 0.5, "Annealing ratio [0.5]")
flags.DEFINE_integer("anneal_period", 25, "Number of epochs for every annealing [25]")

# Common options
flags.DEFINE_boolean("train", True, "Train? Train if true [False]")
flags.DEFINE_boolean("test",False,"Test? Test if True")
flags.DEFINE_boolean("real_time",False,"run in real time?")
flags.DEFINE_boolean("load", False, "Load from saved model? [False]")
flags.DEFINE_boolean("progress", True, "Show progress? [True]")
flags.DEFINE_boolean("gpu", False, 'Enable GPU? (Linux only) [False]')
flags.DEFINE_integer("val_period", 5, "Val period (for display purpose only) [5]")
flags.DEFINE_integer("save_period", 10, "Save period [10]")

# Debugging
flags.DEFINE_boolean("draft", False, "Draft? (quick build) [False]")

# Specific training parameters
flags.DEFINE_integer("memory_size", 50, "Memory size [50]")
flags.DEFINE_integer("hidden_size", 50, "Embedding dimension [20]")
flags.DEFINE_integer("num_layers", 1, "Number of memory layers (hops) [3]")
flags.DEFINE_boolean("linear_start", False, "Start training with linear model? [False]")
flags.DEFINE_float("ls_init_lr", 0.005, "Initial learning rate for linear start [0.005]")
flags.DEFINE_integer("ls_num_epochs", 20, "Linear start duration [20]")
flags.DEFINE_float("max_grad_norm", 40, "Max gradient norm; above this number is clipped [40]")
flags.DEFINE_boolean("position_encoding", False, "Position encoding enabled? 'True' or 'False' [True]")
flags.DEFINE_string("tying", 'rnn', "Indicate tying method: 'adj' or 'rnn' [adj]")

# Specific options
flags.DEFINE_string("data_group",'cust',"Running model on: 'babi' or 'amazon' [babi]")
flags.DEFINE_string("task", 1, "Task number [1]")
flags.DEFINE_float("val_ratio", 0.1, "Validation data ratio to training data [0.1]")

FLAGS = flags.FLAGS




'''
Initialize training of the model
pass in story_text and faq_text raw to be preprocessed in the read_data script
use user_id and story_id to name the final save file so that it can be loaded
'''
def train_model(story_text, faq_text, user_id, story_id):
    train_ds, idx_to_word = read_data.read_train(1, story_text, faq_text)
    print("training dataset: ", train_ds)
    train_ds = train_ds[0]
    train_ds, val_ds = read_data.split_val(train_ds, FLAGS.val_ratio)
    train_ds.name, val_ds.name = 'train', 'val'

    FLAGS.vocab_size = train_ds.vocab_size
    FLAGS.max_sent_size, FLAGS.max_ques_size = read_data.get_max_sizes(train_ds, val_ds)
    FLAGS.max_sent_size = max(FLAGS.max_sent_size, FLAGS.max_ques_size)
    FLAGS.train_num_batches = train_ds.num_batches
    FLAGS.val_num_batches = val_ds.num_batches
    # make a separate save file for each user
    save_dir = path = os.path.dirname(os.path.abspath(__file__))+"/save/"+str(user_id)+"_models"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir) # the s for recursive function
    FLAGS.save_dir = save_dir

    # save the vocab_map and idx_to_word so that it can be loaded when its time to predict
    vocab_save_dir = save_dir + "/vocab"
    if not os.path.exists(vocab_save_dir):
        os.makedirs(vocab_save_dir)

    with open(vocab_save_dir+'/vocab_map.json', 'w') as f:
        json.dump(train_ds.vocab_map, f)

    with open(vocab_save_dir+'/idx_to_word.json','w') as f:
        json.dump(idx_to_word, f)

    if FLAGS.linear_start:
        FLAGS.num_epochs = FLAGS.ls_num_epochs
        FLAGS.init_lr = FLAGS.ls_init_lr

    if FLAGS.draft:
        FLAGS.num_layers = 1
        FLAGS.num_epochs = 1
        FLAGS.eval_period = 1
        FLAGS.ls_duration = 1
        FLAGS.train_num_batches = 1
        FLAGS.test_num_batches = 1
        FLAGS.save_period = 1

    graph = tf.Graph()
    name = ""+str(user_id)+"_"+str(story_id)
    model = n2nModel(graph, FLAGS, name)
    with tf.Session(graph=graph) as sess:
        sess.run(tf.initialize_all_variables())
        writer = tf.train.SummaryWriter(FLAGS.log_dir, sess.graph)
        if FLAGS.load:
            model.load(sess)
        print("training the model")
        model.train(sess, writer, train_ds, val_ds, idx_to_word)

def get_prediction(story_text, faq_text, user_id, story_id, user_folder_path, model_to_load):

    # load the right vocab_map and idx_to_word dictionaries from json
    # save the vocab_map and idx_to_word so that it can be loaded when its time to predict
    save_dir = path = os.path.dirname(os.path.abspath(__file__))+"/save/"+str(user_id)+"_models"
    FLAGS.save_dir = save_dir

    vocab_save_dir = save_dir + "/vocab"
    if not os.path.exists(vocab_save_dir):
        os.makedirs(vocab_save_dir)

    with open(vocab_save_dir+'/vocab_map.json', 'r') as f:
        vocab_map = json.load(f)

    with open(vocab_save_dir+'/idx_to_word.json','r') as f:
        idx_to_word = json.load(f)


    eval_ds, idx_to_word = read_data.read_predict(1, story_text, faq_text, vocab_map, idx_to_word)
    print("eval dataset: ", eval_ds)
    eval_ds = eval_ds[0]
    # eval_ds, val_ds = read_data.split_val(eval_ds, FLAGS.val_ratio)
    eval_ds.name = 'train'
    FLAGS.vocab_size = eval_ds.vocab_size
    FLAGS.max_sent_size, FLAGS.max_ques_size = read_data.get_max_sizes(eval_ds)
    FLAGS.max_sent_size = max(FLAGS.max_sent_size, FLAGS.max_ques_size)
    FLAGS.train_num_batches = eval_ds.num_batches
    # FLAGS.val_num_batches = val_ds.num_batches


    if FLAGS.linear_start:
        FLAGS.num_epochs = FLAGS.ls_num_epochs
        FLAGS.init_lr = FLAGS.ls_init_lr

    if FLAGS.draft:
        FLAGS.num_layers = 1
        FLAGS.num_epochs = 1
        FLAGS.eval_period = 1
        FLAGS.ls_duration = 1
        FLAGS.train_num_batches = 1
        FLAGS.test_num_batches = 1
        FLAGS.save_period = 1

    graph = tf.Graph()
    name = ""+str(user_id)+"_"+str(story_id)
    model = n2nModel(graph, FLAGS, name)
    predicted_answer = ""
    with tf.Session(graph=graph) as sess:
        sess.run(tf.initialize_all_variables())
        model.load(sess)
        predicted_answer, idx_map = model.predict_answer(sess, eval_ds, idx_to_word)

    # pass the predicted answer back through to the api function
        # and then pass it again as the response to the api request
    return predicted_answer, idx_map
