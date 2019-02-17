import tensorflow as tf
import tensorflow.contrib.layers as nn

import numpy as np
flags = tf.app.flags
FLAGS = flags.FLAGS
class RNN():
    def __init__(self, sess):
        self.sess=sess
        self.model_folder='models/RNN/'

        #HYPERPARAMETERS
        self.sequence_length=FLAGS.sequence_length
        self.latent_dimension=FLAGS.latent_dimension
        self.hidden_units=FLAGS.hidden_units
        self.num_layers=FLAGS.LSTM_layers

        self.X=tf.placeholder(tf.float32, shape=[None, None, self.latent_dimension+ FLAGS.actions_size])
        
        self.buildGraph()
        self.buildLoss()
        self.buildUtils()

        self.saver=tf.train.Saver()

        if not(FLAGS.training_RNN):
            self.saver.restore(self.sess, self.model_folder+"graph.ckpt")
            print('RNN weights have been restored')
        else:
            self.sess.run(tf.global_variables_initializer())

    
    def buildGraph(self):
        #initialize init state
        self.init_state=tf.placeholder(tf.float32, [self.num_layers, 2, None, self.hidden_units])

        with tf.variable_scope('LSTM'):        
            init_state = tuple([tf.nn.rnn_cell.LSTMStateTuple(
                self.init_state[l][0],
                self.init_state[l][1]) 
                for l in range(self.num_layers)])

            layers=[]
            for i in range(self.num_layers):
                #Define the LSTM cell with the number of hidden units
                cell=tf.nn.rnn_cell.LSTMCell(self.hidden_units, name="LSTM_"+str(i))
                layers.append(cell)

            self.lstm_cell = tf.contrib.rnn.MultiRNNCell(layers)

            #Feed an input of shape [batch_size, 10, state_rep_length]
            #self.output is a tensor of shape [batch_size, 100, hidden_units]
            #hidden_cell_statesTuple is a list of 2 elements: self.cell_state, self.hidden_state where self.output[:, -1, :]=self.cell_state
            self.output, self.hidden_cell_statesTuple=tf.nn.dynamic_rnn(cell=self.lstm_cell, inputs=self.X, initial_state=init_state)

        flat=tf.reshape(self.output, (-1, self.hidden_units), name="flat_LSTM_output")

        with tf.variable_scope('MLP'):        
            self.flat1=nn.fully_connected(flat, 256)

        with tf.variable_scope('state_output'):        
            self.mean=nn.fully_connected(self.flat1, self.latent_dimension)
            self.stddev=nn.fully_connected(self.flat1, self.latent_dimension, activation_fn=tf.nn.softplus)
            self.next_state_out=self.mean + self.stddev * tf.random.normal([self.latent_dimension])
        
        with tf.variable_scope('reward_output'):
            self.reward_out=nn.fully_connected(self.flat1, 1)
    
    def buildLoss(self):
        self.true_next_state=tf.placeholder(tf.float32, shape=[None, None, self.latent_dimension+1])
        with tf.variable_scope('prepare_labels'):
            true_next=tf.reshape(self.true_next_state, (-1, self.latent_dimension+1))
            true_next_state, true_reward=tf.split(true_next, [self.latent_dimension,1], 1)

        with tf.variable_scope('representation_loss'):
            '''
            self.term1=true_next_state*tf.log(self.next_state_out + 1e-9)
            self.term2= (1-true_next_state)*tf.log(1-self.next_state_out + 1e-9)
            summ=tf.reduce_sum(self.term1 + self.term2, axis=-1)
            '''
            self.representation_loss=tf.reduce_mean(tf.reduce_sum(tf.square(true_next_state - self.next_state_out),axis=-1))
        with tf.variable_scope('reward_loss'):        
            self.reward_loss=tf.reduce_mean(tf.square(true_reward -self.reward_out))

        self.loss=self.representation_loss + self.reward_loss

        self.opt=tf.train.AdamOptimizer(learning_rate=1e-4).minimize(self.loss)
    
    def buildUtils(self):
        self.file=tf.summary.FileWriter(self.model_folder, self.sess.graph)
        self.training=tf.summary.merge([
            tf.summary.scalar('RNN_state_loss', self.representation_loss),
            tf.summary.scalar('RNN_rew_loss', self.reward_loss),
            tf.summary.scalar('RNN_tot_loss', self.loss)
        ])

        self.playing=tf.summary.merge([
            tf.summary.scalar('RNN_game_state_loss', self.representation_loss),
            tf.summary.scalar('RNN_game_rew_loss', self.reward_loss),
            tf.summary.scalar('RNN_game_tot_loss', self.loss)
        ])

        self.totLossPlace=tf.placeholder(tf.float32)

        self.testing=tf.summary.merge([
            tf.summary.scalar('RNN_test_loss',self.totLossPlace)
        ])
    
    def save(self):
        self.saver.save(self.sess, self.model_folder+"graph.ckpt")

    def predict(self, input, initialize=[]):
        if (len(initialize)==0):
            #initialize hidden state and cell state to zeros 
            initialize=np.zeros((self.num_layers, 2, input.shape[0], self.hidden_units))

        nextStates, rew, hidden_state=self.sess.run([self.next_state_out, self.reward_out,self.hidden_cell_statesTuple], feed_dict={self.X: input,
                                                             self.init_state: initialize})

        return np.concatenate((nextStates,rew),axis=-1), hidden_state[0]