"""
Tests for basic phygnn model interface functionality and execution.
"""
# pylint: disable=W0613
import os
import numpy as np
import pandas as pd
import pytest
import tensorflow as tf
from tensorflow.keras.layers import (InputLayer, Dense, Activation)
import shutil

from phygnn import PhysicsGuidedNeuralNetwork, TESTDATADIR
from phygnn.model_interfaces.phygnn_model import PhygnnModel


FPATH = os.path.join(TESTDATADIR, '_temp_model', '_temp_model.pkl')

N = 100
A = np.linspace(-1, 1, N)
B = np.linspace(-1, 1, N)
A, B = np.meshgrid(A, B)
A = np.expand_dims(A.flatten(), axis=1)
B = np.expand_dims(B.flatten(), axis=1)

Y = np.sqrt(A ** 2 + B ** 2)
X = np.hstack((A, B))
FEATURES = pd.DataFrame(X, columns=['a', 'b'])
P = X.copy()
Y_NOISE = Y * (1 + (np.random.random(Y.shape) - 0.5) * 0.5) + 0.1
LABELS = pd.DataFrame(Y_NOISE, columns=['c'])


HIDDEN_LAYERS = [{'units': 64, 'activation': 'relu', 'name': 'relu1'},
                 {'units': 64, 'activation': 'relu', 'name': 'relu2'}]


def p_fun_pythag(model, y_true, y_predicted, p):
    """Example function for loss calculation using physical relationships.

    Parameters
    ----------
    model : PhysicsGuidedNeuralNetwork
        Instance of the phygnn model at the current point in training.
    y_true : np.ndarray
        Known y values that were given to the PhyGNN fit method.
    y_predicted : tf.Tensor
        Predicted y values in a 2D tensor based on x values in this batch.
    p : np.ndarray
        Supplemental physical feature data that can be used to calculate a
        y_physical value to compare against y_predicted. The rows in this
        array have been carried through the batching process alongside y_true
        and the FEATURES used to create y_predicted and so can be used 1-to-1
        with the rows in y_predicted and y_true.

    Returns
    -------
    p_loss : tf.Tensor
        A 0D tensor physical loss value.
    """

    p = tf.convert_to_tensor(p, dtype=tf.float32)
    y_physical = tf.sqrt(p[:, 0]**2 + p[:, 1]**2)
    y_physical = tf.expand_dims(y_physical, 1)

    p_loss = tf.math.reduce_mean(tf.math.abs(y_predicted - y_physical))

    return p_loss


def test_nn():
    """Test the basic NN operation of the PGNN without weighting pfun."""
    PhysicsGuidedNeuralNetwork.seed(0)
    model = PhygnnModel.build_trained(p_fun_pythag, FEATURES, LABELS, P,
                                      normalize=False,
                                      hidden_layers=HIDDEN_LAYERS,
                                      loss_weights=(1.0, 0.0),
                                      n_batch=4,
                                      n_epoch=20)

    test_mae = np.mean(np.abs(model.predict(X, table=False) - Y))

    loss = 0.15
    assert len(model.layers) == 6
    assert len(model.weights) == 6
    assert len(model.history) == 20
    assert model.history.validation_loss.values[-1] < loss
    assert test_mae < loss


def test_phygnn_model():
    """Test the operation of the PGNN with weighting pfun."""
    PhysicsGuidedNeuralNetwork.seed(0)
    model = PhygnnModel.build_trained(p_fun_pythag, FEATURES, LABELS, P,
                                      normalize=False,
                                      hidden_layers=HIDDEN_LAYERS,
                                      loss_weights=(0.0, 1.0),
                                      n_batch=4,
                                      n_epoch=20)

    test_mae = np.mean(np.abs(model.predict(X, table=False) - Y))

    loss = 0.019
    assert len(model.layers) == 6
    assert len(model.weights) == 6
    assert len(model.history) == 20
    assert isinstance(model.layers[0], InputLayer)
    assert isinstance(model.layers[1], Dense)
    assert isinstance(model.layers[2], Activation)
    assert isinstance(model.layers[3], Dense)
    assert isinstance(model.layers[4], Activation)
    assert isinstance(model.layers[5], Dense)
    assert model.history.validation_loss.values[-1] < loss
    assert test_mae < loss


def test_normalize():
    """Test the operation of the PGNN with weighting pfun."""
    PhysicsGuidedNeuralNetwork.seed(0)
    model = PhygnnModel.build_trained(p_fun_pythag, FEATURES, LABELS, P,
                                      normalize=False,
                                      hidden_layers=HIDDEN_LAYERS,
                                      loss_weights=(0.0, 1.0),
                                      n_batch=4,
                                      n_epoch=20)

    test_mae = np.mean(np.abs(model.predict(X, table=False) - Y))

    loss = 0.015
    assert model.history.validation_loss.values[-1] < loss
    assert test_mae < loss


def test_save_load():
    """Test the save/load operations of PhygnnModel"""
    PhysicsGuidedNeuralNetwork.seed(0)
    model = PhygnnModel.build_trained(p_fun_pythag, FEATURES, LABELS, P,
                                      normalize=False,
                                      hidden_layers=HIDDEN_LAYERS,
                                      loss_weights=(0.0, 1.0),
                                      n_batch=4,
                                      n_epoch=20,
                                      save_path=FPATH)
    y_pred = model[X]

    loaded = PhygnnModel.load(FPATH)
    y_pred_loaded = loaded[X]
    np.allclose(y_pred.values, y_pred_loaded.values)
    assert loaded.feature_names == ['a', 'b']
    assert loaded.label_names == ['c']
    shutil.rmtree(os.path.dirname(FPATH))


def test_OHE():
    """
    Test one-hot encoding
    """
    ohe_features = FEATURES.copy()
    categories = list('def')
    ohe_features['categorical'] = np.random.choice(categories, len(FEATURES))
    one_hot_categories = {'categorical': categories}
    x = ohe_features.values

    PhysicsGuidedNeuralNetwork.seed(0)
    model = PhygnnModel.build_trained(p_fun_pythag, ohe_features, LABELS, P,
                                      one_hot_categories=one_hot_categories,
                                      hidden_layers=HIDDEN_LAYERS,
                                      loss_weights=(0.0, 1.0),
                                      n_batch=4,
                                      n_epoch=20)

    assert all(np.isin(categories, model.feature_names))
    assert not any(np.isin(categories, model.input_feature_names))
    assert 'categorical' not in model.feature_names
    assert 'categorical' in model.input_feature_names

    out = model.predict(x)
    assert 'c' in out


def test_bad_categories():
    """
    Test OHE checks
    """
    one_hot_categories = {'categorical': list('abc')}
    feature_names = FEATURES.columns.tolist() + ['categorical']
    label_names = 'c'
    with pytest.raises(RuntimeError):
        PhygnnModel.build(p_fun_pythag, feature_names, label_names,
                          one_hot_categories=one_hot_categories,
                          hidden_layers=HIDDEN_LAYERS,
                          loss_weights=(0.0, 1.0))

    one_hot_categories = {'categorical': list('cdf')}
    feature_names = FEATURES.columns.tolist() + ['categorical']
    label_names = 'c'
    with pytest.raises(RuntimeError):
        PhygnnModel.build(p_fun_pythag, feature_names, label_names,
                          one_hot_categories=one_hot_categories,
                          hidden_layers=HIDDEN_LAYERS,
                          loss_weights=(0.0, 1.0))

    one_hot_categories = {'categorical': list('def')}
    feature_names = FEATURES.columns.tolist() + ['categories']
    label_names = 'c'
    with pytest.raises(RuntimeError):
        PhygnnModel.build(p_fun_pythag, feature_names, label_names,
                          one_hot_categories=one_hot_categories,
                          hidden_layers=HIDDEN_LAYERS,
                          loss_weights=(0.0, 1.0))

    one_hot_categories = {'cat1': list('def'), 'cat2': list('fgh')}
    feature_names = FEATURES.columns.tolist() + ['cat1', 'cat2']
    label_names = 'c'
    with pytest.raises(RuntimeError):
        PhygnnModel.build(p_fun_pythag, feature_names, label_names,
                          one_hot_categories=one_hot_categories,
                          hidden_layers=HIDDEN_LAYERS,
                          loss_weights=(0.0, 1.0))

    ohe_features = FEATURES.copy()
    categories = list('def')
    ohe_features['categorical'] = np.random.choice(categories, len(FEATURES))
    one_hot_categories = {'categorical': categories}
    x = ohe_features.values[:, 1:]
    PhysicsGuidedNeuralNetwork.seed(0)
    model = PhygnnModel.build_trained(p_fun_pythag, ohe_features, LABELS, P,
                                      one_hot_categories=one_hot_categories,
                                      hidden_layers=HIDDEN_LAYERS,
                                      loss_weights=(0.0, 1.0),
                                      n_batch=4,
                                      n_epoch=20)
    with pytest.raises(RuntimeError):
        model.predict(x)
