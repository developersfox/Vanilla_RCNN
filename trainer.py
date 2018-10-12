import resources
import torch
import random
import numpy as np

import Vanilla

from torch                     \
    import Tensor
from torch.multiprocessing       \
    import Pool

from Vanilla                          \
    import update_model_rmsprop        \
    as optimize_model

loss_fn = Vanilla.loss_wrt_distance



    # filter struct


filters = Vanilla.default_filters


    # basic params


epochs = 20
learning_rate = 0.001

batch_size = 400 ; data_size = batch_size*2
data_path = "samples_*.pkl"

train_basic = True


    # advanced params


rms_alpha = 0.9

adam_alpha_moment = 0.9
adam_alpha_accugrad = 0.999

dropout = 0.0

loss_nultip = (1, 0.001, 0.001, 0.001)

    # # #


def train_rms(model, accu_grads, data, num_epochs=1):

    num_samples = len(data)
    num_batches = int(num_samples / batch_size)
    num_workers = torch.multiprocessing.cpu_count()

    losses = []

    for epoch in range(num_epochs):

        epoch_loss = np.zeros(Vanilla.hm_vectors)

        random.shuffle(data)

        for batch in range(num_batches):

            # create batch

            batch_loss = np.zeros_like(epoch_loss)

            batch_ptr = batch * batch_size
            batch_end_ptr = (batch+1) * batch_size
            batch = data[batch_ptr:batch_end_ptr]

            with Pool(num_workers) as pool:

                # create procs

                results = pool.map_async(process_fn, [[model.copy(), batch[_]] for _ in range(batch_size)])

                pool.close()

                # retrieve procs

                pool.join()

                for result in results.get():
                    loss, grads = result

                    Vanilla.apply_grads(model,grads)
                    batch_loss += loss

                # handle

                epoch_loss += batch_loss

            optimize_model(model, accu_grads, batch_size=batch_size, lr=learning_rate, alpha=rms_alpha)

        losses.append(epoch_loss)
        # ; print(f'epoch {epoch} loss {epoch_loss}') ; resources.write_loss_training(epoch_loss, True, epoch)
    return model, accu_grads, losses


def process_fn(fn_input):

    model, data = fn_input
    x_vocab, x_oct, x_dur, x_vol, y_vocab, y_oct, y_dur, y_vol = data
    generative_length = len(y_vocab)

    inp = [x_vocab, x_oct, x_dur, x_vol]
    trg = [[Tensor(e) for e in [y_vocab[_], y_oct[_], y_dur[_], y_vol[_]]]
           for _ in range(generative_length)]

    response = Vanilla.forward_prop(model, inp, gen_iterations=generative_length, filters=filters, dropout=dropout)

    sequence_losses = loss_fn(response, trg)

    loss = [float(sum(element)) for element in sequence_losses]

    Vanilla.update_gradients(sequence_losses, loss_multipliers=loss_nultip)

    grads = Vanilla.return_grads(model)

    return loss, grads


    #   Helpers   #


def init_accugrads(model):
    accu_grads = []
    for layer in model:
        layer_accus = []
        for _ in layer.keys():
            layer_accus.append(0)
        accu_grads.append(layer_accus)
    return accu_grads

def save_accugrads(accu_grads, model_id=None):
    model_id = '' if model_id is None else str(model_id)
    resources.pickle_save(accu_grads, 'model' + model_id + '_accugrads.pkl')

def load_accugrads(model, model_id=None):
    model_id = '' if model_id is None else str(model_id)
    try:
        accu_grads = resources.pickle_load('model' + model_id + '_accugrads.pkl')
        print('> accugrads.pkl loaded.')
    except:
        print('> accugrads.pkl not found.')
        accu_grads = init_accugrads(model)
    return accu_grads


def init_moments(model):
    moments = []
    for layer in model:
        layer_moments = []
        for _ in layer.keys():
            layer_moments.append(0)
        moments.append(layer_moments)
    return moments

def save_moments(moments, model_id=None):
    model_id = '' if model_id is None else str(model_id)
    resources.pickle_save(moments, 'model' + model_id + '_moments.pkl')

def load_moments(model, model_id=None):
    model_id = '' if model_id is None else str(model_id)
    try:
        moments = resources.pickle_load('model' + model_id + '_moments.pkl')
        print('> moments.pkl loaded.')
    except:
        print('> moments.pkl not found.')
        moments = init_moments(model)
    return moments



    #   Alternative Trainers     #



def train_adam(model, accu_grads, moments, data, epoch_nr=None, num_epochs=1):

    num_samples = len(data)
    num_batches = int(num_samples / batch_size)
    num_workers = torch.multiprocessing.cpu_count()

    losses = []

    for epoch in range(num_epochs):

        epoch_loss = np.zeros(Vanilla.vector_size)

        random.shuffle(data)

        for batch in range(num_batches):

            # create batch

            batch_loss = np.zeros_like(epoch_loss)

            batch_ptr = batch * batch_size
            batch_end_ptr = (batch+1) * batch_size
            batch = np.array(data[batch_ptr:batch_end_ptr])

            with Pool(num_workers) as pool:

                # create procs

                results = pool.map_async(process_fn, [[model.copy(), batch[_]] for _ in range(batch_size)])

                pool.close()

                # retrieve procs

                pool.join()

                for result in results.get():
                    loss, grads = result

                    Vanilla.apply_grads(model,grads)
                    batch_loss -= loss

                # handle

                epoch_loss += batch_loss

            if epoch_nr is None: epoch_nr = epoch
            Vanilla.update_model_adam(model, accu_grads, moments, epoch_nr, batch_size=batch_size, lr=learning_rate, alpha_moments=adam_alpha_moment, alpha_accugrads=adam_alpha_accugrad)

        losses.append(epoch_loss)

    return model, accu_grads, moments, losses





if __name__ == '__main__':

    torch.set_default_tensor_type('torch.FloatTensor')

    data = resources.load_data(data_path, data_size)
    IOdims = resources.vocab_size

    # # here is a sample datapoint (X & Y)..
    # print('X:')
    # for thing in data[0][0:4]: print(thing)
    # print('Y:')
    # for thing in data[0][4:]: print(thing)

    if train_basic:

        # RMS basic training

        model = resources.load_model()
        if model is None: model = Vanilla.create_model(filters)

        accu_grads = load_accugrads(model)

        model, accu_grads, losses = train_rms(
            model,
            accu_grads,
            data,
            num_epochs=epochs)

        resources.save_model(model)
        save_accugrads(accu_grads)

    else:

        # ADAM advanced training

        model = res.load_model()
        if model is None: model = Vanilla.create_model(filters)

        accu_grads = load_accugrads(model)
        moments = load_moments(model)

        model, accu_grads, moments, losses = train_adam(
            model,
            accu_grads,
            moments,
            data,
            num_epochs=epochs)

        resources.save_model(model)
        save_accugrads(accu_grads)
        save_moments(moments)
