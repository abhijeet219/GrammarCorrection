#!/usr/bin/env python
# -*- coding: utf-8 -*-


from keras.layers import *
from keras.models import *

from models import config


class AttentionDecoder(Layer):

    def __init__(self, rnn_cell, **kwargs):

        self.output_dim = rnn_cell.state_size[0]
        self.rnn_cell = rnn_cell
        super(AttentionDecoder, self).__init__(**kwargs)

    def call(self, input):

        inputs, context_mat = input

        def step(inputs, states):
            hid = states[0]
            ctx_vec, att_weigts = self.attend(hid, context_mat, self.contextMatTimeSteps, self.att_kernel,
                                              self.att_kernel_2)
            rnn_inp = K.concatenate((inputs, ctx_vec), axis=1)
            return self.rnn_cell.call(rnn_inp, states)

        timesteps = K.int_shape(inputs)[1]

        initial_state = self.get_initial_state(inputs)

        last_output, outputs, states = K.rnn(step,
                                             inputs,
                                             initial_state,
                                             input_length=timesteps)

        return outputs

    def build(self, input_shape):
        assert type(input_shape) is list
        assert len(input_shape) == 2

        self.att_kernel = self.add_weight(name='att_kernel_1',
                                          shape=(self.output_dim + input_shape[1][2], input_shape[1][2]),
                                          initializer='uniform',
                                          trainable=True)

        self.att_kernel_2 = self.add_weight(name='att_kernel_2',
                                            shape=(input_shape[1][2], 1),
                                            initializer='uniform',
                                            trainable=True)

        step_input_shape = (
            input_shape[0][0], input_shape[0][2] + input_shape[1][2])  # batch_size , in_dim + contextVecDim
        self.rnn_cell.build(step_input_shape)

        self._trainable_weights += self.rnn_cell.trainable_weights
        self._non_trainable_weights += self.rnn_cell.non_trainable_weights

        self.contextMatTimeSteps = input_shape[1][1]

        super(AttentionDecoder, self).build(input_shape)

    def get_initial_state(self, inputs):

        initial_state = K.zeros_like(inputs)
        initial_state = K.sum(initial_state, axis=(1, 2))
        initial_state = K.expand_dims(initial_state)
        if hasattr(self.rnn_cell.state_size, '__len__'):
            return [K.tile(initial_state, [1, dim]) for dim in self.rnn_cell.state_size]
        else:
            return [K.tile(initial_state, [1, self.rnn_cell.state_size])]

    def get_context_vec(self, context_mat, att_weigts):
        att_weigts_rep = K.expand_dims(att_weigts, 2)
        att_weigts_rep = K.repeat_elements(att_weigts_rep, context_mat.shape[2], 2)
        return K.sum(att_weigts_rep * context_mat, axis=1)

    def attend(self, key_vec, context_mat, contextMatTimeSteps, w1, w2):
        key_rep = K.repeat(key_vec, contextMatTimeSteps)
        concated = K.concatenate([key_rep, context_mat], axis=-1)
        concated_r = K.reshape(concated, (-1, concated.shape[-1]))
        att_energies = K.dot((K.dot(concated_r, w1)), w2)
        att_energies = K.relu(K.reshape(att_energies, (-1, contextMatTimeSteps)))
        att_weigts = K.softmax(att_energies)

        return self.get_context_vec(context_mat, att_weigts), att_weigts

    def compute_output_shape(self, input_shape):
        return input_shape[0][0], input_shape[0][1], self.output_dim


def getModel(embedding, word_index):
    """
    According to the "Massive Exploration of Neural Machine Translation Architectures"
    best params for NMT models (seq2seq framework) are
    encoder/decoder depths are size of 4, embedding size 512, attention dim 512
    """

    enc_seq_length = config.MAX_SEQ_LEN
    enc_vocab_size = min(len(word_index), config.MAX_VOCAB_SIZE) + 1
    dec_seq_length = config.MAX_SEQ_LEN
    dec_vocab_size = min(len(word_index), config.MAX_VOCAB_SIZE) + 1

    inp = Input((enc_seq_length,))
    imp_x = Embedding(enc_vocab_size, config.WORD_EMBEDDING_DIM, weights=[embedding], trainable=False)(inp)

    ctxmat0 = Bidirectional(LSTM(100, return_sequences=True))(imp_x)

    inp_cond = Input((dec_seq_length,))
    inp_cond_x = Embedding(dec_vocab_size, config.WORD_EMBEDDING_DIM, weights=[embedding], trainable=False)(inp_cond)

    inp_cxt = Bidirectional(LSTM(100, return_sequences=True))(inp_cond_x)

    decoded = AttentionDecoder(LSTMCell(100))([inp_cxt, ctxmat0])

    decoded = TimeDistributed(Dense(dec_vocab_size, activation='softmax'))(decoded)

    model = Model([inp, inp_cond], decoded)
    model.compile('nadam', 'categorical_crossentropy')
    print(model.summary())

    return model
