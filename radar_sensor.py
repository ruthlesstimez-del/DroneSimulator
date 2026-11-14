"""Game-only radar abstraction: range/visibility gating, scan cadence, noisy contacts."""
import math

import numpy as np


class RadarSensor:
    def __init__(self, range_m=80.0, scan_seconds=1.0, hold_seconds=1.8, noise_m=.35, seed=12):
        self.range_m=range_m
        self.scan_seconds=scan_seconds
        self.hold_seconds=hold_seconds
        self.noise_m=noise_m
        self.rng=np.random.default_rng(seed)
        self.next_scan=0.0
        self.last_seen=None
        self.contact=None
        self.last_scan_valid=False
        self.scans=0

    def due(self,now):
        return now>=self.next_scan

    def update(self,observer,target,visible,now):
        if self.due(now):
            self.scans+=1
            self.next_scan=now+self.scan_seconds
            delta=np.asarray(target,dtype=float)-np.asarray(observer,dtype=float)
            self.last_scan_valid=bool(visible and np.linalg.norm(delta)<=self.range_m)
            if self.last_scan_valid:
                measured=np.asarray(target,dtype=float)+self.rng.normal(0,self.noise_m,3)
                self.contact=measured.tolist()
                self.last_seen=now
        if self.last_seen is None or now-self.last_seen>self.hold_seconds:
            self.contact=None
        return self.contact

    def report(self,observer,now):
        contact=self.contact
        if self.last_seen is not None and now-self.last_seen>self.hold_seconds:
            contact=None
        delta=None if contact is None else np.asarray(contact)-np.asarray(observer)
        return {'status':'searching' if contact is None else ('tracking' if self.last_scan_valid else 'coasting'),
                'range_m':self.range_m,'scan_seconds':self.scan_seconds,
                'hold_seconds':self.hold_seconds,'position_noise_m':self.noise_m,
                'contact':contact,'contact_age':None if contact is None else round(now-self.last_seen,2),
                'measured_range_m':None if delta is None else float(np.linalg.norm(delta)),
                'bearing_degrees':None if delta is None else math.degrees(math.atan2(delta[1],delta[0]))%360,
                'elevation_degrees':None if delta is None else math.degrees(math.atan2(-delta[2],math.hypot(delta[0],delta[1]))),
                'sweep_degrees':(now%self.scan_seconds)/self.scan_seconds*360,'scans':self.scans,
                'model':'Game sensor abstraction; 360-degree samples, not RF radar simulation.'}
