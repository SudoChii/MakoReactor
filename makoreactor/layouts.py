import cadquery as cq

from dataclasses import dataclass
import numpy as np
from affine import Affine
import warnings



class Layout(): 
  layout_affine = Affine.translation(0,0) # identity
  
  @property
  def geom(self):
    raise NotImplementedError("Please Impliment me :(") 
  
  @property
  def layout(self):      
    raise NotImplementedError("Please Impliment me :(") 

  def tolist(self):
    return self.layout.tolist()

  def __mul__(self, val:Affine):
    self.layout_affine *= val
    return self
  
  def __rmul__(self, val:Affine):
    self.layout_affine = val * self.layout_affine
    return self
  
  def __iter__(self):
    return self.layout.__iter__()

  def __next__(self):
    return self.layout.tolist().__next__()
  
  def __repr__(self):
    return str(list(self.layout))

  def __str__(self):
    return str(list(self.layout))



class CircleCapLeverless(Layout): 
  """
  F1CapLayout 

  Layout for circular Frame 1 caps, similar to the GCCMX layout but only one center button for start.
  """
  
  right_homerow_coords = [(-26.15, -11.75), (0,0), (26.65, -3.2), (53.3, -19.45), 
                          (-26.15, -33.75), (0, -22), (26.65, -25.2), (53.3, -41.45)]
    
  # the four buttons for directionals is just the first 4 buttons reflected along the Y axis
  left_homerow_coords = np.dot(right_homerow_coords[4:], [[-1, 0], [0, 1]])
    
  right_thumb_coords = [(0,0), (-18.5, -12.75), (0, 25.5), (-18.5, 12.75), (18.5, 12.75)]
  # modifier buttons are just the first two cstick buttons reflected along the Y axis
  left_thumb_coords = np.dot(right_thumb_coords[:2], [[-1, 0], [0, 1]])
  misc_coords = [(0,0)]

  right_homerow_affine = Affine.translation(100, 58)
  left_homerow_affine = Affine.translation(-100, 58)
  left_thumb_affine = Affine.translation(-70, -45)
  right_thumb_affine = Affine.translation(70, -45)
  misc_affine = Affine.translation(0, 18)
  cap_diameter = 22.5
  intersection_fillet = 0.5
  
  
  @property
  def layout(self):
    # concat them to return the complete list
    coords = [self.left_homerow_layout, 
                      self.right_homerow_layout, 
                      self.left_thumb_layout, 
                      self.right_thumb_layout, 
                      self.misc_layout]
    
    coords = [c for c in coords if len(c)]
    layout = np.concatenate(coords, axis=0)
    layout = np.asarray([self.layout_affine * c for c in layout])
    return layout.tolist()
 
  @property
  def geom(self):
    def create_sketch(points): 
      if len(list(points)) == 0:
          # basically disable this part of the layout
          return None
      else:  
          points = np.asarray([self.layout_affine * p for p in points])
          s = (
              cq.Sketch()
              .push(points.tolist())
              .circle(self.cap_diameter/2) # this uses radius
              .clean()
              .reset()
          )
          try: 
              s = s.vertices().fillet(self.intersection_fillet)
          except Exception as e:
              # failed to add fillet, usually because the circles dont intersect
              pass 
          return s
    
    s0 = create_sketch(self.left_thumb_layout)
    s1 = create_sketch(self.right_thumb_layout)
    s2 = create_sketch(self.left_homerow_layout) 
    s3 = create_sketch(self.right_homerow_layout)
    s4 = create_sketch(self.misc_layout)
    
    sketches = [s0, s1, s2, s3, s4]
    sketches = [s for s in sketches if s]
    geom = cq.Workplane().placeSketch(*sketches)
    return geom 
 
  @property
  def left_homerow_layout(self): 
    if len(self.left_homerow_coords) == 0:
      return [] 
    assert len(np.asarray(self.left_homerow_coords).shape) == 2
    return [self.left_homerow_affine * c for c in self.left_homerow_coords]


  @property
  def right_homerow_layout(self): 
    if len(self.right_homerow_coords) == 0:
        return []
    assert len(np.asarray(self.right_homerow_coords).shape) == 2
    return [self.right_homerow_affine * c for c in self.right_homerow_coords]


  @property
  def left_thumb_layout(self): 
    if len(self.left_thumb_coords) == 0:
        return []
    assert len(np.asarray(self.left_thumb_coords).shape) == 2
    return [self.left_thumb_affine * c for c in self.left_thumb_coords]


  @property
  def right_thumb_layout(self):
    if len(self.right_thumb_coords) == 0:
        return []
    assert len(np.asarray(self.right_thumb_coords).shape) == 2
    return [self.right_thumb_affine * c for c in self.right_thumb_coords]


  @property
  def misc_layout(self): 
    if len(self.misc_coords) == 0:
      return []
    assert len(np.asarray(self.misc_coords).shape) == 2
    return [self.misc_affine * c for c in self.misc_coords]


class SquareCapLeverless(CircleCapLeverless):   
  cap_dimensions:tuple[float] = (20.5, 20.5)
  cap_fillet_radius:float = .1
  
  @property
  def geom(self):                             
     if len(list(self.layout)) == 0:          
       return Base.generate(self)               
                                              
     s = (                                    
         cq.Sketch()                          
             .push(self.layout)         
             .rect(*self.cap_dimensions)   
             .clean()                         
             .reset()                         
             .vertices()                   
             .fillet(self.cap_fillet_radius)
     )

     return cq.Workplane().placeSketch(s)


class Gccmx(CircleCapLeverless):
  """
  GccmxLayout A layout mimicing Crane's GCCMX layout

  This is the same as the default layout except there are 
  three buttons in the center to suppport things like a home and share buttons 
  when combining a brook with a ModelS.
  """
  misc_coords = [(-20, 0), (0,0), (20, 0)]


class FgcLeverless(CircleCapLeverless):
    left_thumb_coords = [(0,0)]
    right_thumb_coords = []
    left_homerow_coords = CircleCapLeverless().left_homerow_coords[:-1]
    right_homerow_coords = [(-26.15, -14), (0,0), (26.65, 0), (53.3, -7), 
                          (-26.15, -43.0), (0, -29), (26.65, -29), (53.3, -36)]
    misc_coords = [(-26.16, 0), (0,0), (26.16, 0)]
    
    right_homerow_affine =  Affine.rotation(0) * Affine.translation(40, 45)
    left_homerow_affine = Affine.rotation(0) * Affine.translation(-40, 50)
    left_thumb_affine = Affine.translation(0, -30)
    misc_affine = Affine.translation(-90, 57)
    
  
smashGccmxLayout = Gccmx()
smashF1CapLayout = CircleCapLeverless()
smashKeycapLayout = SquareCapLeverless()
fgcF1CapLayout = FgcLeverless()
