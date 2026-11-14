"""Bind vehicle-specific RPCs to one simulated vehicle, leaving world APIs alone."""
import functools
import inspect


class VehicleClient:
    def __init__(self, client, vehicle):
        self.client = client
        self.vehicle = vehicle

    def __getattr__(self, name):
        function = getattr(self.client, name)
        if not callable(function) or 'vehicle_name' not in inspect.signature(function).parameters:
            return function
        @functools.wraps(function)
        def bound(*args, **kwargs):
            kwargs.setdefault('vehicle_name', self.vehicle)
            return function(*args, **kwargs)
        setattr(self, name, bound)
        return bound
