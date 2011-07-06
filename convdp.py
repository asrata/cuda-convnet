# Abstract feed-forward neural net
# 
# Author: Alex Krizhevsky (akrizhevsky@gmail.com)

from data import *
import numpy.random as nr

class CIFARDataProvider(LabeledMemoryDataProvider):
    def __init__(self, data_dir, batch_range, init_epoch=1, init_batchnum=None, dp_params={}, test=False):
        LabeledMemoryDataProvider.__init__(self, data_dir, batch_range, init_epoch, init_batchnum, dp_params, test)
        
    def get_next_batch(self):
        epoch, batchnum, datadic = LabeledMemoryDataProvider.get_next_batch(self)
        data_mean = self.batch_meta['data_mean']
        
        if 'processed' not in datadic:
            datadic['data'] = n.require((datadic['data'].astype(n.single) - data_mean), dtype=n.single, requirements='C')# / 255
            datadic['labels'] = datadic['labels'].reshape((1, datadic['data'].shape[1]))
                
            datadic['processed'] = True

        return epoch, batchnum, [datadic['data'], datadic['labels']]

    def get_data_dims(self, idx=0):
        return 3072 if idx == 0 else 1
    
class CroppedCIFARDataProvider(LabeledMemoryDataProvider):
    def __init__(self, data_dir, batch_range=None, init_epoch=1, init_batchnum=None, dp_params=None, test=False):
        LabeledMemoryDataProvider.__init__(self, data_dir, batch_range, init_epoch, init_batchnum, dp_params, test)

        self.border_size = dp_params['crop_border']
        self.inner_size = 32 - self.border_size*2
        self.multiview = dp_params['multiview_test'] and test
        self.num_views = 9
        self.data_mult = self.num_views if self.multiview else 1
        
        for d in self.data_dic:
            d['data'] = n.require(d['data'], requirements='C')
            d['labels'] = n.require(n.tile(d['labels'].reshape((1, d['data'].shape[1])), (1, self.data_mult)), requirements='C')
        
        self.cropped_data = [n.zeros((self.get_data_dims(), self.data_dic[0]['data'].shape[1]*self.data_mult), dtype=n.single) for x in xrange(2)]

        self.batches_generated = 0
        self.data_mean = self.batch_meta['data_mean'].reshape((3,32,32))[:,self.border_size:self.border_size+self.inner_size,self.border_size:self.border_size+self.inner_size].reshape((self.get_data_dims(), 1))

    def get_next_batch(self):
        epoch, batchnum, datadic = LabeledMemoryDataProvider.get_next_batch(self)

        cropped = self.cropped_data[self.batches_generated % 2]

        self.__trim_borders(datadic['data'], cropped)
        cropped -= self.data_mean
        self.batches_generated += 1
        return epoch, batchnum, [cropped, datadic['labels']]
        
    def get_data_dims(self, idx=0):
        return self.inner_size**2 * 3 if idx == 0 else 1

    def __trim_borders(self, x, target):
        y = x.reshape(3, 32, 32, x.shape[1])

        if self.test: # don't need to loop over cases
            if self.multiview:
                start_positions = [(0,0), (0, self.border_size), (0, self.border_size*2),
                                  (self.border_size, 0), (self.border_size, self.border_size), (self.border_size, self.border_size*2),
                                  (self.border_size*2, 0), (self.border_size*2, self.border_size), (self.border_size*2, self.border_size*2)]
                end_positions = [(sy+self.inner_size, sx+self.inner_size) for (sy,sx) in start_positions]
                for i in xrange(self.num_views):
                    target[:,i * x.shape[1]:(i+1)* x.shape[1]] = y[:,start_positions[i][0]:end_positions[i][0],start_positions[i][1]:end_positions[i][1],:].reshape((self.get_data_dims(),x.shape[1]))
            else:
                pic = y[:,self.border_size:self.border_size+self.inner_size,self.border_size:self.border_size+self.inner_size, :] # just take the center for now
                target[:,:] = pic.reshape((self.get_data_dims(), x.shape[1]))
        else:
            for c in xrange(x.shape[1]): # loop over cases
                # translate with 50% chance
                startY, startX = nr.randint(0,self.border_size*2 + 1), nr.randint(0,self.border_size*2 + 1)
                endY, endX = startY + self.inner_size, startX + self.inner_size
                pic = y[:,startY:endY,startX:endX, c]
                if nr.randint(2) == 0: # also flip the image with 50% probability
                    pic = pic[:,:,::-1]
                target[:,c] = pic.reshape((self.get_data_dims(),))
    
class DummyConvNetDataProvider(LabeledDummyDataProvider):
    def __init__(self, data_dim):
        LabeledDummyDataProvider.__init__(self, data_dim)
        
    def get_next_batch(self):
        epoch, batchnum, dic = LabeledDummyDataProvider.get_next_batch(self)
        
        dic['data'] = n.require(dic['data'].T, requirements='C')
        dic['labels'] = n.require(dic['labels'].T, requirements='C')
        
        return epoch, batchnum, [dic['data'], dic['labels']]

    def get_data_dims(self, idx=0):
        return self.batch_meta['num_vis'] if idx == 0 else 1