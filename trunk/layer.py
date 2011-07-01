# Abstract feed-forward neural net
# 
# Author: Alex Krizhevsky (akrizhevsky@gmail.com)

import options as op
import sys
import ConfigParser as cfg
import os
import numpy as n
import numpy.random as nr
from math import ceil
from ordereddict import OrderedDict

def make_weights(numRows, numCols, init, order='C'):
    weights = n.array(init * nr.randn(numRows, numCols), dtype=n.single, order=order)
    weights_inc = n.zeros_like(weights)
    return weights, weights_inc

class LayerParsingError(Exception):
    pass

# Subclass that throws more convnet-specific exceptions than the default
class MyConfigParser(cfg.SafeConfigParser):
    def get(self, section, option):
        return self.safeGet(section, option)
    
    def safeGet(self, section, option, f=cfg.SafeConfigParser.get, typestr=None):
        try:
            return f(self, section, option)
        except cfg.NoOptionError, e:
            raise LayerParsingError("Layer '%s': required parameter '%s' missing" % (section, option))
        except ValueError, e:
            if typestr is None:
                raise e
            raise LayerParsingError("Layer '%s': parameter '%s' must be %s" % (section, option, typestr))
        
    def safeGetList(self, section, option, f, typestr=None):
        v = self.safeGet(section, option)
        try:
            return [f(x) for x in v.split(',')]
        except:
            raise LayerParsingError("Layer '%s': parameter '%s' must be ','-delimited list of %s" % (section, option, typestr))
        
    def getint(self, section, option):
        return self.safeGet(section, option, cfg.SafeConfigParser.getint, 'int')
        
    def getfloat(self, section, option):
        return self.safeGet(section, option, cfg.SafeConfigParser.getfloat, 'float')
    
    def getbool(self, section, option):
        return self.safeGet(section, option, cfg.SafeConfigParser.getbool, 'bool')
    
    def getFloatList(self, section, option):
        return self.safeGetList(section, option, float, typestr='floats')
    
    def getIntList(self, section, option):
        return self.safeGetList(section, option, int, typestr='ints')
    
    def getBoolList(self, section, option):
        return self.safeGetList(section, option, bool, typestr='bools')
                     
class LayerParser:
    @classmethod
    def requires_params(cls):
        return False
        
    @classmethod
    def add_params(cls, name, mcp, dic):
        pass
    
    @classmethod
    def parse(cls, name, mcp, prev_layers, model):
        dic = {}
        dic['name'] = name
        dic['type'] = mcp.get(name, 'type')

        return dic
        
    @staticmethod
    def parse_layers(layer_cfg_path, param_cfg_path, model, layers=[]):
        try:
            if not os.path.exists(layer_cfg_path):
                raise LayerParsingError("Layer definition file '%s' does not exist" % layer_cfg_path)
            if not os.path.exists(param_cfg_path):
                raise LayerParsingError("Layer parameter file '%s' does not exist" % param_cfg_path)
            if len(layers) == 0:
                mcp = MyConfigParser(dict_type=OrderedDict)
                mcp.read([layer_cfg_path])
                for name in mcp.sections():
                    if not mcp.has_option(name, 'type'):
                        raise LayerParsingError("Layer '%s': no type given" % name)
                    ltype = mcp.get(name, 'type')
                    if ltype not in layer_parsers:
                        raise LayerParsingError("Layer '%s': Unknown layer type: '%s'" % (name, ltype))
                    layers += [layer_parsers[ltype].parse(name, mcp, layers, model)]
            
            for l in layers:
                if not l['type'].startswith('cost.'):
                    found = max(l['name'] in [layers[n]['name'] for n in l2['inputs']] for l2 in layers if 'inputs' in l2)
                    if not found:
                        raise LayerParsingError("Layer '%s' of type '%s' is unused" % (l['name'], l['type']))

            mcp = MyConfigParser(dict_type=OrderedDict)
            mcp.read([param_cfg_path])
            
            for i in xrange(len(layers)):
                name = layers[i]['name']
                ltype = layers[i]['type']
                lp = layer_parsers[ltype]
                if not mcp.has_section(name) and lp.requires_params():
                    raise LayerParsingError("Layer '%s' of type '%s' requires extra parameters, but none given in file '%s'." % (name, ltype, param_cfg_path))
                lp.add_params(name, mcp, layers[i])
        except LayerParsingError, e:
            print e
            sys.exit(1)
         
        return layers
        
    @staticmethod
    def register_layer_parser(ltype, cls):
        if ltype in layer_parsers:
            raise LayerParsingError("Layer type '%s' already registered" % ltype)
        layer_parsers[ltype] = cls

# Any layer that takes an input (i.e. non-data layer)
class LayerWithInputParser(LayerParser):
    @classmethod
    def parse(cls, name, mcp, prev_layers, model):
        dic = LayerParser.parse(name, mcp, prev_layers, model)
        
        dic['inputs'] = [inp.strip() for inp in mcp.get(name, 'inputs').split(',')]
        prev_names = [p['name'] for p in prev_layers]
        for inp in dic['inputs']:
            if inp not in prev_names:
                raise LayerParsingError("Layer '%s': input '%s' not defined" % (name, inp))
        dic['inputs'] = [prev_names.index(inp) for inp in dic['inputs']]
        dic['numInputs'] = [prev_layers[i]['numOutputs'] for i in dic['inputs']]
        
        return dic

class FCLayerParser(LayerWithInputParser):
    @classmethod
    def requires_params(cls):
        return True
    
    @classmethod
    def verifyNumParams(cls, dic, param):
        if len(dic[param]) != len(dic['inputs']):
            raise LayerParsingError("Layer '%s': %s list length does not match number of inputs" % (dic['name'], param))
    
    @classmethod
    def add_params(cls, name, mcp, dic):
        dic['epsW'] = mcp.getFloatList(name, 'epsW')
        dic['epsB'] = mcp.getfloat(name, 'epsB')
        dic['momW'] = mcp.getFloatList(name, 'momW')
        dic['momB'] = mcp.getfloat(name, 'momB')
        dic['wc'] = mcp.getFloatList(name, 'wc')
        
        FCLayerParser.verifyNumParams(dic, 'epsW')
        FCLayerParser.verifyNumParams(dic, 'momW')
        FCLayerParser.verifyNumParams(dic, 'wc')
    
    @classmethod
    def parse(cls, name, mcp, prev_layers, model):
        dic = LayerWithInputParser.parse(name, mcp, prev_layers, model)

        dic['numOutputs'] = mcp.getint(name, 'numOutputs')
        dic['neuron'] = mcp.get(name, 'neuron')
        dic['initW'] = mcp.getFloatList(name, 'initW')

        FCLayerParser.verifyNumParams(dic, 'initW')
        
        weights = [make_weights(numIn, dic['numOutputs'], init, order='F') for numIn,init in zip(dic['numInputs'], dic['initW'])]
        biases = make_weights(1, dic['numOutputs'], 0, order='F')
        dic['weights'] = [w[0] for w in weights]
        dic['weightsInc'] = [w[1] for w in weights]
        dic['biases'] = biases[0]
        dic['biasesInc'] = biases[1]
        
        print "Initialized fully-connected layer '%s', producing %d outputs" % (name, dic['numOutputs'])
        return dic

class ConvLayerParser(LayerWithInputParser):
    @classmethod
    def requires_params(cls):
        return True
    
    @classmethod
    def add_params(cls, name, mcp, dic):
        dic['epsW'] = mcp.getfloat(name, 'epsW')
        dic['epsB'] = mcp.getfloat(name, 'epsB')
        dic['momW'] = mcp.getfloat(name, 'momW')
        dic['momB'] = mcp.getfloat(name, 'momB')
        dic['wc'] = mcp.getfloat(name, 'wc')
    
    @classmethod
    def parse(cls, name, mcp, prev_layers, model):
        dic = LayerWithInputParser.parse(name, mcp, prev_layers, model)
        if len(dic['numInputs']) != 1:
            raise LayerParsingError("Layer '%s': number of inputs must be 1", name) 
        dic['channels'] = mcp.getint(name, 'channels')
        dic['imgPixels'] = dic['numInputs'][0] / dic['channels']
        dic['imgSize'] = int(n.sqrt(dic['imgPixels']))
        if dic['numInputs'][0] % dic['imgPixels'] != 0 or dic['imgSize'] * dic['imgSize'] != dic['imgPixels']:
            raise LayerParsingError("Layer '%s': has %-d dimensional input, not interpretable as %d-channel images" % (name, dic['numInputs'][0], dic['channels']))
        if dic['channels'] > 3 and dic['channels'] % 4 != 0:
            raise LayerParsingError("Layer '%s': number of channel channels must be smaller than 4 or divisible by 4" % name)
        
        dic['padding'] = mcp.getint(name, 'padding')
        dic['stride'] = mcp.getint(name, 'stride')
        dic['filterSize'] = mcp.getint(name, 'filterSize')
        dic['filterPixels'] = dic['filterSize']**2
        dic['modulesX'] = 1 + int(ceil((2 * dic['padding'] + dic['imgSize'] - dic['filterSize']) / float(dic['stride'])))
        dic['modules'] = dic['modulesX']**2
        dic['numFilters'] = mcp.getint(name, 'numFilters')
        dic['numOutputs'] = dic['modules'] * dic['numFilters']
        dic['partialSum'] = mcp.getint(name, 'partialSum')
        if dic['partialSum'] != 0 and dic['modules'] % dic['partialSum'] != 0:
            raise LayerParsingError("Layer '%s': convolutional layer produces %d outputs per filter, but given partialSum parameter (%d) does not divide this number" % (name, dic['modules'], dic['partialSum']))
        
        dic['padding'] = -dic['padding']
        dic['neuron'] = mcp.get(name, 'neuron')
        dic['initW'] = mcp.getfloat(name, 'initW')
        
        dic['weights'], dic['weightsInc'] = make_weights(dic['filterPixels']*dic['channels'], \
                                                         dic['numFilters'], dic['initW'], order='C')
        dic['biases'], dic['biasesInc'] = make_weights(dic['modules']*dic['numFilters'], 1, 0, order='C')
        
        print "Initialized convolutional layer '%s', producing %dx%d %d-channel output" % (name, dic['modulesX'], dic['modulesX'], dic['numFilters'])
        
        return dic    
    
class DataLayerParser(LayerParser):
    @classmethod
    def parse(cls, name, mcp, prev_layers, model):
        dic = LayerParser.parse(name, mcp, prev_layers, model)
        dic['dataIdx'] = mcp.getint(name, 'dataIdx')
        dic['numOutputs'] = model.train_data_provider.get_data_dims(idx=dic['dataIdx'])
        
        print "Initialized data layer '%s', producing %d outputs" % (name, dic['numOutputs'])
        return dic

class SoftmaxLayerParser(LayerWithInputParser):
    @classmethod
    def parse(cls, name, mcp, prev_layers, model):
        dic = LayerWithInputParser.parse(name, mcp, prev_layers, model)
        if len(dic['numInputs']) != 1:
            raise LayerParsingError("Layer '%s': Number of inputs must be 1", name)
        dic['numOutputs'] = prev_layers[dic['inputs'][0]]['numOutputs']
        print "Initialized softmax layer '%s', producing %d outputs" % (name, dic['numOutputs'])
        return dic

class PoolLayerParser(LayerWithInputParser):
    @classmethod
    def parse(cls, name, mcp, prev_layers, model):

        dic = LayerWithInputParser.parse(name, mcp, prev_layers, model)
        if len(dic['numInputs']) != 1:
            raise LayerParsingError("Layer '%s': number of inputs must be 1", name) 
        dic['channels'] = mcp.getint(name, 'channels')
        dic['subsX'] = mcp.getint(name, 'subsX')
        dic['start'] = mcp.getint(name, 'start')
        dic['stride'] = mcp.getint(name, 'stride')
        dic['outputsX'] = mcp.getint(name, 'outputsX')
        dic['stride'] = mcp.getint(name, 'stride')
        dic['pool'] = mcp.get(name, 'pool')
        
        if dic['channels'] % 16 != 0:
            raise LayerParsingError("Layer '%s': parameter 'channels' must be multiple of 16")
        
        if dic['pool'] not in ('max', 'avg'):
            raise LayerParsingError("Layer '%s': parameter 'pool' must be one of 'max', 'avg'", name)
        
        dic['imgPixels'] = dic['numInputs'][0] / dic['channels']
        dic['imgSize'] = int(n.sqrt(dic['imgPixels']))
        if dic['numInputs'][0] % dic['imgPixels'] != 0 or dic['imgSize'] * dic['imgSize'] != dic['imgPixels']:
            raise LayerParsingError("Layer '%s': has %-d dimensional input, not interpretable as %d-channel images" % (name, dic['numInputs'][0], dic['channels']))
        if dic['outputsX'] <= 0:
            dic['outputsX'] = int(ceil((dic['imgSize'] - dic['start'] - dic['subsX']) / float(dic['stride']))) + 1;
        dic['numOutputs'] = dic['outputsX']**2 * dic['channels']
        
        print "Initialized %s-pooling layer '%s', producing %dx%d %d-channel output" % (dic['pool'], name, dic['outputsX'], dic['outputsX'], dic['channels'])
        return dic
    
class CostParser(LayerWithInputParser):
    @classmethod
    def requires_params(cls):
        return True    
    
    @classmethod
    def add_params(cls, name, mcp, dic):
        dic['coeff'] = mcp.getfloat(name, 'coeff')
            
class LogregCostParser(CostParser):
    @classmethod
    def parse(cls, name, mcp, prev_layers, model):
        dic = CostParser.parse(name, mcp, prev_layers, model)
        
        if len(dic['numInputs']) != 2: # the inputs are labels, predicted probabilities
            raise LayerParsingError("Layer '%s': Number of inputs must be 2: labels and predicted probabilities", name)
        if dic['numInputs'][0] != 1: # first input must be labels
            raise LayerParsingError("Layer '%s': Dimensionality of first input must be 1", name)
        
        print "Initialized logistic regression cost '%s'" % name
        return dic
    
layer_parsers = {'data': DataLayerParser,
                 'fc': FCLayerParser,
                 'conv': ConvLayerParser,
                 'softmax': SoftmaxLayerParser,
                 'pool': PoolLayerParser,
                 'cost.logreg': LogregCostParser}