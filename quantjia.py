# coding=utf-8

from __future__ import absolute_import
import datetime
import os
import numpy as np
import pandas as pd

from DataManager import *
from ModelManager import *
from keras.models import load_model
from keras.callbacks import ModelCheckpoint, EarlyStopping, TensorBoard
from datetime import date
from datetime import timedelta
from keras.utils import plot_model
import sys


def parse_params(mstr):
    # M1_T5_B256_C3_E100_Lmin_Mgem_K5
    # build_model1, lookback=5, batch_size = 256, catf = catnorm_data, epoch=100, label = 'min', mem = 'gem'

    catf = {'C3':'catf3', 'C4':'catf4', 'C2':'catf2','C22':'catf22', 'C31':'catf31','C32':'catf32','C1':'noncatf'}
    models = {'M1':'build_model', 'M2':'build_model2', 'M3':'build_model3', 'M4':'build_model4', 'M5':'build_model5', 'MK':'nbuild_model'}
    params = {}
    params['mclass'] = ''
    params['model_name'] = mstr
    params['metrics'] = ['categorical_accuracy']
    params['cmetrics'] = {'recall':recall, 'top1_recall':top1_recall, 'top_t1p1':top_t1p1}
    params['main_metric'] = {'top_t1p1':top_t1p1}
    params['totals'] = 5

    mstr_arr = str(mstr).upper().split('_')
    for s in mstr_arr:
        if s.startswith('M'):
            params['model'] = models[s]
            params['mclass'] = params['mclass']+s
        if s.startswith('T'):
            params['lookback'] = int(s[1:])
        if s.startswith('B'):
            params['batch_size'] = int(s[1:])
        if s.startswith('C'):
            params['catf'] = catf[s]
            params['mclass'] = params['mclass'] + s[0:2]
            params['outdim'] = int(s[1:2])
            if int(s[1:2]) >= 3:
                params['cmetrics']['top_t2p1'] = top_t2p1
                # params['cmetrics']['top2_recall'] = top2_recall
                # params['main_metric'] = {'top_t2p1': top_t2p1}
        if s.startswith('E'):
            params['epoch'] = int(s[1:])
        if s.startswith('L'):
            params['mclass'] = params['mclass'] + s
            params['label'] = s[1:].lower()
        if s.startswith('M'):
            params['mem'] = s[1:]
        if s.startswith('K'):
            params['ktype'] = s[1:]
    params['metrics'].extend(sorted(params['cmetrics'].values()))
    return params


def ntrain_model(mstr, start, mid, end):
    params = parse_params(mstr)
    print ("[ train model ]... " + mstr)

    labcol_map = {'o2c':-4, 'close': -3, 'min': -2, 'max': -1}
    labelcol = labcol_map[params['label']]
    index = ['sme', 'gem']
    # index = None

    train = ncreate_dataset(index=index, days=params['lookback'], start=start, end=mid, ktype=params['ktype'])
    test = ncreate_dataset(index=index, days=params['lookback'], start=mid, end=end, ktype=params['ktype'])

    # dataset = ncreate_dataset(index=None,days=params['lookback'], start=start, end=end, ktype=params['ktype'])
    # train, test = split_dataset(dataset, 0.75, params['batch_size'])

    bstrain, tstrain, lbtrain_v = create_feeddata(train)
    bstest, tstest, lbtest_v = create_feeddata(test)

    train_x = tstrain
    train_y = eval(params['catf'])(lbtrain_v[:, labelcol])
    train_y, train_x, non = balance_data(train_y, train_x)

    sz = len(train_y)/params['batch_size'] * params['batch_size']
    train_x = train_x[:sz]
    train_y = train_y[:sz]

    test_x = tstest
    test_y = eval(params['catf'])(lbtest_v[:,labelcol])
    test_y_v = lbtest_v
    balance_data(test_y, test_x)

    params['indim'] = train_x.shape[- 1]

    path = 'models/' + params['mclass']+ '/'+params['model_name']
    model_dir = os.path.dirname(path)
    if not os.path.exists(model_dir): os.makedirs(model_dir)

    if __debug__:
        patience = 2
    else:
        patience = 1000

    logdir =datetime.datetime.now().strftime(path+'/S'+start+'.%Y%m%d.%H.%M.%S.run')
    path = logdir

    callbacks = [
        EarlyStopping(monitor='val_loss', patience=patience, verbose=0, mode='min'),
        ModelCheckpoint(path+'/best_model.h5', monitor='val_'+params['main_metric'].keys()[0], save_best_only=True, verbose=0, mode='max'),
        TensorBoard(log_dir=logdir, histogram_freq=0, write_graph=False, write_images=False),
    ]
    model = eval(params['model'])(params)
    print "model summary"
    model.summary()
    model.fit(train_x, train_y, batch_size=params['batch_size'], epochs=params['epoch'],validation_split=0.33,callbacks=callbacks)
              # validation_data=(test_x, test_y), callbacks=callbacks)
    save_model(model, path + '/model.h5')

    if params['catf'] == 'noncatf':
        return None
    else:
        # print '使用最终模型进行预测'
        # proba = model.predict_proba(test_x, verbose=0, batch_size=params['batch_size'])
        #
        # out = np.hstack([proba, test_y_v])
        # sortout = out[(-out[:, proba.shape[-1] - 1]).argsort(), :]
        # if not __debug__:
        #     np.savetxt(path + "/val_result.txt", sortout, fmt='%f')
        #
        # print_dist_cut(sortout, proba.shape[-1]-1,labelcol,20,mstr)

        print '使用最优模型进行预测'
        model = load_model(path + '/best_model.h5', custom_objects=params['cmetrics'])
        proba = model.predict_proba(test_x, verbose=0, batch_size=params['batch_size'])

        out = np.hstack([proba, test_y_v])
        sortout = out[(-out[:, proba.shape[-1] - 1]).argsort(), :]
        if not __debug__:
            np.savetxt(path + "/val_result.txt", sortout, fmt='%f')

        print_dist_cut(sortout, proba.shape[-1]-1,labelcol,20,path)
        print_dist(sortout, proba.shape[-1] - 1, labelcol, 10)

    print "[ End train model ]"


def nvalid_model(mstr, run=None, start=(datetime.date.today() - timedelta(days=60)).strftime('%Y-%m-%d'), end=None):
    print ("[ valid model: %s ]... with data from %s to %s"%(mstr,start, end))
    params = parse_params(mstr)
    path = 'models/' + params['mclass'] + '/' + params['model_name']
    if run is not None:
        path = path + '/' + run
    model = load_model(path+'/best_model.h5',custom_objects=params['cmetrics'])
    print "model summary"
    model.summary()

    labcol_map = {'close': -3, 'min': -2, 'max': -1}
    labelcol = labcol_map[params['label']]

    dataset = ncreate_dataset(days=params['lookback'], start=start, end=end, ktype=params['ktype'])
    bs, ts, lb_v = create_feeddata(dataset)
    y = eval(params['catf'])(lb_v[:, labelcol])
    sz = len(y)/params['batch_size'] * params['batch_size']
    x = ts[:sz]
    y = y[:sz]
    lb_v = lb_v[:sz]

    proba = model.predict_proba(x, verbose=0, batch_size=params['batch_size'])
    out = np.hstack([proba, lb_v])
    sortout = out[(-out[:, proba.shape[ - 1] - 1]).argsort(), :]

    print_dist(sortout, proba.shape[ - 1] - 1, labelcol,20)
    print_dist_cut(sortout, proba.shape[ - 1] - 1, labelcol,20)

    if not __debug__:
        np.savetxt(path + "/best_model."+start+"."+end+".txt", sortout, fmt='%f')
    else:
        print sortout[0:200, :]

    print ("[ End validate model: %s ]... " % (mstr))
    # return sortout


def predict_batch():
    file = os.path.realpath(__file__)
    os.chdir(os.path.dirname(file))
    print os.path.dirname(file)
    path = "./models/confirm/"
    for model in os.listdir(path):
        if os.path.isdir(path+model):
            if os.path.exists(path+model + '/model.h5'):
                predict_today(model, path)


def predict_today(mstr, path='./models/'):
    print ("[ select stocks ]... using model:" + mstr)
    params = parse_params(mstr)
    model = load_model(path+params['model_name']+'/model.h5',custom_objects=params['cmetrics'])

    tsdata, rtdata_v = create_today_dataset(params['lookback'])
    batch_size = params['batch_size']
    data_x = tsdata[:len(tsdata) / batch_size * batch_size]
    data_v = rtdata_v[:len(rtdata_v) / batch_size * batch_size]
    proba = model.predict_proba(data_x, verbose=0, batch_size=batch_size)
    out = np.column_stack([proba, data_v[:,:]])
    sortout = out[(-out[:, proba.shape[proba.ndim - 1] - 1]).argsort(), :]

    if not __debug__:
        dt = (datetime.date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
        np.savetxt(path + params['model_name'] + "/"+dt+"_result.txt", sortout, fmt='%f')
    else:
        print sortout[0:20, :]

    idx = params['outdim'] - 1
    sortout = sortout[sortout[:,idx]>=0.5][:,(idx+1, -4, idx)]
    candidates = pd.DataFrame(sortout, columns=('code','price', 'proba'))
    print "[ End prediction ] of tomorrow's price"
    return candidates


def print_model(mstr):
    params = parse_params(mstr)
    model = load_model('./models/'+params['model_name']+'/best_model.h5',custom_objects=params['cmetrics'])
    print "model summary"
    model.summary()
    plot_model(model, to_file='model.png', show_shapes=True, show_layer_names=True)


def get_stats(group):
    return {'min':group.min(), 'max':group.max(), 'count':group.count(), 'mean':group.mean()}


def print_dist(proba, sortcol, labelcol, b=10.0):
    # print mean p_change of the proba result
    bins = np.arange(0, 1, 1/float(b))
    labels = bins.searchsorted(proba[:, sortcol])
    grouped = pd.Series(proba[:, labelcol]).groupby(labels)
    print grouped.apply(get_stats).unstack()
    if dir is not None:
        pass
        # pd.DataFrame(grouped.apply(get_stats).unstack()).to_csv("./models/" + dir + "/dist.txt")
    # end print


def print_dist_cut(proba, sortcol, labelcol, b=10.0,dir=None):
    # print mean p_change of the proba result
    factor = pd.cut(proba[:, sortcol],b)
    grouped = pd.Series(proba[:, labelcol]).groupby(factor)
    print grouped.apply(get_stats).unstack()
    if dir is not None:
        # pd.DataFrame(grouped.apply(get_stats).unstack()).to_csv(dir + "/dist.txt")
        pass
    # end print


def _main_():
    if len(sys.argv) > 6:
        eval(sys.argv[1])(sys.argv[2], sys.argv[3], sys.argv[4],sys.argv[5],sys.argv[5])
    elif len(sys.argv) > 5:
        eval(sys.argv[1])(sys.argv[2], sys.argv[3], sys.argv[4],sys.argv[5])
    elif len(sys.argv) > 4:
        eval(sys.argv[1])(sys.argv[2], sys.argv[3], sys.argv[4])
    elif len(sys.argv) > 3:
        eval(sys.argv[1])(sys.argv[2], sys.argv[3])
    elif len(sys.argv) > 2:
        eval(sys.argv[1])(sys.argv[2])
    else:
        eval(sys.argv[1])()
    exit(0)


if __name__ == '__main__':
    _main_()
    # M1T5C3_D1()
    # predict_today()

