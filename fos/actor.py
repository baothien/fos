import numpy as np

from pyglet.gl import *
from ctypes import *

from PySide.QtOpenGL import QGLShader, QGLShaderProgram
from PySide.QtGui import QMatrix4x4, QVector3D

from vsml import vsml
from .shader.lib import *

class Actor(object):

    def __init__(self):

        # is this actor currently visible
        self.visible = True

        # is this actor currently selected
        self.selected = False

        # affine transformation of the actor
        # relative to the Region it is associated with
        self.transformation = None

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False


class DynamicActor(Actor):

    def __init__(self):
        """ Dynamic actor either implemented as a list
        of static actors, or with data arrays having a temporal dimension
        """

        # is the actor currently playing
        self.playing = False

        # the reference to the first time frame
        self.current_time_frame = 0

    def next(self):
        """ Next time step
        """
        pass

    def previous(self):
        """ Previous time step
        """
        pass

    def play(self):
        """ Start playing
        """
        pass

    def pause(self):
        """ Pause playing
        """
        pass

    def stop(self):
        """ Stop playing and reset to start
        """
        pass

class ScaleBar(object):

    def __init__(self):
        """ ScaleBar actor with text
        """
        pass

class AABB(object):

    def __init__(self):
        """ Axis Aligned Bounding Box
        """
        pass

class CartesianCoordianteSystemAxes(object):

    def __init__(self):
            """ Actor displaying the three cartesian, orthogonal coordinates
            """
            pass

def modelview_matrix(array_type=c_float, glGetMethod=glGetFloatv):
    """
    Returns the current modelview matrix.
    """
    m = (array_type*16)()
    glGetMethod(GL_MODELVIEW_MATRIX, m)
    print "modelview matrix", np.array(m)

def projection_matrix(array_type=c_float, glGetMethod=glGetFloatv):
    """
    Returns the current modelview matrix.
    """
    m = (array_type*16)()
    glGetMethod(GL_PROJECTION_MATRIX, m)
    print "projection matrix", np.array(m)

from fos.shader import get_vary_line_width_shader

class TreeActor(Actor):

    def __init__(self,
                 vertices,
                 connectivity,
                 colors = None,
                 radius = None,
                 affine = None):
        """ A TreeRegion, composed of many trees

        vertices : Nx3
            3D Coordinates x,y,z
        connectivity : Mx1
            Tree topology
        colors : Nx4 or 1x4
            Per connection color
        radius : N
            Per vertex radius
        affine : 4x4
            Affine transformation of the actor

        """
        super(TreeActor, self).__init__()

        if affine is None:
            self.affine = np.eye(4, dtype = np.float32)
        else:
            self.affine = affine
        #self._update_glaffine()

        self.vertices = vertices
        self.connectivity = connectivity

        # unfortunately, we need to duplicate vertices if we want per line color
        self.vertices = self.vertices[self.connectivity,:]

        # we have a simplified connectivity now
        self.connectivity = np.array( range(len(self.vertices)), dtype = np.uint32 )

        # this coloring section is for per/vertex color
        if colors is None:
            # default colors for each line
            self.colors = np.array( [[1.0, 0.0, 0.0, 1.0]], dtype = np.float32).repeat(len(self.connectivity)/2, axis=0)
        else:
            # colors array is half the size of the connectivity array
            assert( len(self.connectivity)/2 == len(colors) )
            self.colors = colors

        # we want per line color
        # duplicating the color array, we have the colors per vertex
        self.colors =  np.repeat(self.colors, 2, axis=0)

        # the sample 1d texture data array
        if not radius is None:
            self.mytex = radius.astype( np.float32 )
        else:
            self.mytex = np.ones( len(self.vertices), dtype = np.float32 )

        # create indicies, seems to be slow with nested loops
        self.indices = self.connectivity
        self.indices_ptr = self.indices.ctypes.data
        self.indices_nr = self.indices.size

        # duplicate colors to make it "per vertex"
        self.colors_ptr = self.colors.ctypes.data

        self.vertices_ptr = self.vertices.ctypes.data
        self.mode = GL_LINES
        self.type = GL_UNSIGNED_INT

        self.shader = get_vary_line_width_shader()

        self.aPosition_loc = self.shader.retrieveAttribLocation( "aPosition" )
        self.aColor_loc = self.shader.retrieveAttribLocation( "aColor" )

        # VBO related
        glVertexAttribPointer(self.aPosition_loc, 3, GL_FLOAT, GL_FALSE, 0, 0)
        self.vertex_vbo = GLuint(0)
        glGenBuffers(1, self.vertex_vbo)
        glBindBuffer(GL_ARRAY_BUFFER_ARB, self.vertex_vbo)
        glBufferData(GL_ARRAY_BUFFER_ARB, 4 * self.vertices.size, self.vertices_ptr, GL_STATIC_DRAW)
        glDisableVertexAttribArray(self.aPosition_loc)

        # for indices
        self.indices_vbo = GLuint(0)
        glGenBuffers(1, self.indices_vbo)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.indices_vbo)
        # uint32 has 4 bytes
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, 4 * self.indices_nr, self.indices_ptr, GL_STATIC_DRAW)

        # for colors
        glVertexAttribPointer(self.aColor_loc, 4, GL_FLOAT, GL_FALSE, 0, 0)
        self.colors_vbo = GLuint(0)
        glGenBuffers(1, self.colors_vbo)
        glBindBuffer(GL_ARRAY_BUFFER, self.colors_vbo)
        glBufferData(GL_ARRAY_BUFFER, 4 * self.colors.size, self.colors_ptr, GL_STATIC_DRAW)
        glDisableVertexAttribArray(self.aColor_loc)

        # check if we allow to enable texture for radius information
        self.tex_size = int( np.sqrt( self.mytex.size ) ) + 1

        # maximum 2d texture
        myint = GLint(0)
        glGetIntegerv(GL_MAX_TEXTURE_SIZE, myint)
        oint = GLint(0)
        glGetIntegerv(GL_MAX_TEXTURE_BUFFER_SIZE_EXT, oint)
        print "Max texture buffer size", oint.value
        self.max_tex = myint.value

        if self.tex_size < self.max_tex:
            self.mytex_ptr = self.mytex.ctypes.data
            self.use_tex = True
            self.mytex.resize( self.tex_size )
            self.mytex_ptr = self.mytex.ctypes.data
            self.init_texture_2d()
        else:
            raise Exception("Too many vertices to use texture for radius mapping")

    def init_texture_2d(self):
        # self.tex_unit = gen_texture()
        self.tex_unit = GLuint()
        glGenTextures(1, byref(self.tex_unit))

        glBindTexture(GL_TEXTURE_2D, self.tex_unit)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        # target, level, internalformat, width, border, format, type, pixels
        glTexImage2D(GL_TEXTURE_2D, 0, GL_LUMINANCE32F_ARB, self.tex_size, self.tex_size, 0, GL_LUMINANCE, GL_FLOAT, self.mytex_ptr)
        glBindTexture(GL_TEXTURE_2D, 0)

    def draw(self):

        # http://www.opengl.org/wiki/GlVertexAttribPointer

        # bind the shader
        self.shader.bind()

        self.shader.uniform_matrixf( 'projMatrix', vsml.get_projection())
        self.shader.uniform_matrixf( 'modelviewMatrix', vsml.get_modelview())

        self.shader.uniformi( 'textureWidth', self.tex_size)
        self.shader.uniformi( 'widthSampler', 0)

        if self.use_tex:
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, self.tex_unit)

        glEnableVertexAttribArray(self.aPosition_loc)
        glBindBuffer(GL_ARRAY_BUFFER_ARB, self.vertex_vbo)
        glVertexAttribPointer(self.aPosition_loc, 3, GL_FLOAT, GL_FALSE, 0, 0)

        glEnableVertexAttribArray(self.aColor_loc)
        glBindBuffer(GL_ARRAY_BUFFER_ARB, self.colors_vbo)
        glVertexAttribPointer(self.aColor_loc, 4, GL_FLOAT, GL_FALSE, 0, 0)

        # bind the indices buffer
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.indices_vbo)

        glDrawElements(self.mode,self.indices_nr,self.type,0)

        glDisableVertexAttribArray(self.aPosition_loc)
        glDisableVertexAttribArray(self.aColor_loc)

        # unbind the shader
        self.shader.unbind()


class PolygonLines(Actor):

    def __init__(self,
             vertices,
             connectivity,
             colors = None,
             radius = None,
             affine = None):
        """ A PolygonLines, composed of many (branching) polygons

        vertices : Nx3
            3D Coordinates x,y,z
        connectivity : Mx1
            Tree topology
        colors : Nx4 or 1x4
            Per connection color
        affine : 4x4
            Affine transformation of the actor

        Notes
        -----
        Only create this actor of a valid OpenGL context exists
        """
        super(PolygonLines, self).__init__()

        self.program = get_shader_program( "propagate", "130" )
        
        self.aPosition = self.program.attributeLocation("aPosition")
        self.aColor = self.program.attributeLocation("aColor")
        
        self.projMatrix = self.program.uniformLocation("projMatrix")
        self.modelviewMatrix = self.program.uniformLocation("modelviewMatrix")

        if affine is None:
            self.affine = np.eye(4, dtype = np.float32)
        else:
            self.affine = affine

        # unfortunately, we need to duplicate vertices if we want per line color
        self.vertices = vertices[connectivity,:]

        # we have a simplified connectivity now
        self.connectivity = np.array( range(len(self.vertices)), dtype = np.uint32 )

        # this coloring section is for per/vertex color
        if colors is None:
            # default colors for each line
            self.colors = np.array( [[1.0, 0.0, 0.0, 1.0]], dtype = np.float32).repeat(len(self.connectivity)/2, axis=0)
        else:
            # colors array is half the size of the connectivity array
            assert( len(self.connectivity)/2 == len(colors) )
            self.colors = colors

        # we want per line color
        # duplicating the color array, we have the colors per vertex
        self.colors =  np.repeat(self.colors, 2, axis=0)

        self.vertices_ptr = self.vertices.ctypes.data
        self.connectivity_ptr = self.connectivity.ctypes.data
        self.connectivity_nr = self.connectivity.size
        self.colors_ptr = self.colors.ctypes.data

        # for vertices location
        glVertexAttribPointer(self.aPosition, 3, GL_FLOAT, GL_FALSE, 0, 0)
        self.vertex_vbo = GLuint(0)
        glGenBuffers(1, self.vertex_vbo)
        glBindBuffer(GL_ARRAY_BUFFER_ARB, self.vertex_vbo)
        glBufferData(GL_ARRAY_BUFFER_ARB, 4 * self.vertices.size, self.vertices_ptr, GL_STATIC_DRAW)
        glDisableVertexAttribArray(self.aPosition)

        # for colors
        glVertexAttribPointer(self.aColor, 4, GL_FLOAT, GL_FALSE, 0, 0)
        self.colors_vbo = GLuint(0)
        glGenBuffers(1, self.colors_vbo)
        glBindBuffer(GL_ARRAY_BUFFER, self.colors_vbo)
        glBufferData(GL_ARRAY_BUFFER, 4 * self.colors.size, self.colors_ptr, GL_STATIC_DRAW)
        glDisableVertexAttribArray(self.aColor)

        # for indices
        self.connectivity_vbo = GLuint(0)
        glGenBuffers(1, self.connectivity_vbo)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.connectivity_vbo)
        # uint32 has 4 bytes
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, 4 * self.connectivity_nr, self.connectivity_ptr, GL_STATIC_DRAW)

        
    def draw(self):

        self.program.bind()

        self.program.setUniformValueArray( self.projMatrix,
            QMatrix4x4( tuple(vsml.projection.ravel().tolist()) ),
            16 )

        self.program.setUniformValueArray( self.modelviewMatrix,
            QMatrix4x4( tuple(vsml.modelview.ravel().tolist()) ),
            16 )

        # http://www.pyside.org/docs/pyside/PySide/QtOpenGL/QGLShaderProgram.html
        self.program.enableAttributeArray( self.aPosition )
        glBindBuffer(GL_ARRAY_BUFFER_ARB, self.vertex_vbo)
        glVertexAttribPointer(self.aPosition, 3, GL_FLOAT, GL_FALSE, 0, 0)

        glEnableVertexAttribArray(self.aColor)
        glBindBuffer(GL_ARRAY_BUFFER_ARB, self.colors_vbo)
        glVertexAttribPointer(self.aColor, 4, GL_FLOAT, GL_FALSE, 0, 0)
        
        # bind the indices buffer
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.connectivity_vbo)

        glDrawElements( GL_LINES, self.connectivity_nr, GL_UNSIGNED_INT, 0 )

        self.program.disableAttributeArray( self.aPosition )

        self.program.release()
    

class Axes(Actor):

    def __init__(self, scale = 10.0):
        """ Draw three axes
        """
        super(Axes, self).__init__()
        self.scale = scale

    def draw(self):
        #glPushMatrix()
        glLineWidth(2.0)
        glBegin (GL_LINES)
        # x axes
        glColor3f(1.0, 0.0, 0.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(self.scale,0.0,0.0)
        # y axes
        glColor3f(0.0, 1.0, 0.0)
        glVertex3f(0.0,0.0,0.0)
        glVertex3f(0.0,self.scale,0.0)
        # z axes
        glColor3f(0.0, 0.0, 1.0)
        glVertex3f(0.0,0.0,0.0)
        glVertex3f(0.0,0.0,self.scale)
        glEnd()
        #glPopMatrix()

class TriangleActor(Actor):
    def __init__(self):
        super(TriangleActor, self).__init__()

    def draw(self):
        glColor3f(1.0, 0.0, 1.0)
        glBegin(GL_QUADS)
        x1 = +0.06
        y1 = -0.14
        x2 = +0.14
        y2 = -0.06
        x3 = +0.08
        y3 = +0.00
        x4 = +0.30
        y4 = +0.22
        self.quad(x1, y1, x2, y2, y2, x2, y1, x1)
        glEnd()

    def quad(self, x1, y1, x2, y2, x3, y3, x4, y4):
        glVertex3d(x1, y1, -0.05)
        glVertex3d(x2, y2, -0.05)
        glVertex3d(x3, y3, -0.05)
        glVertex3d(x4, y4, -0.05)

        glVertex3d(x4, y4, +0.05)
        glVertex3d(x3, y3, +0.05)
        glVertex3d(x2, y2, +0.05)
        glVertex3d(x1, y1, +0.05)


class PolygonLinesOLD(Actor):

    def __init__(self,
                 vertices,
                 connectivity,
                 colors = None):
        """ A PolygonLines, a generic irregular data structure

        vertices : Nx3
            Local 3D coordinates x,y,z
        connectivity : Mx2
            Polygon line topology
        colors : Nx4 or 1x4, float [0,1]
            Color per vertex

        """
        super(PolygonLines, self).__init__()

        self.vertices = vertices
        self.connectivity = connectivity.ravel()

        # this coloring section is for per/vertex color
        if colors is None:
            # default colors for each line
            self.colors = np.array( [[1.0, 0.0, 0.0, 1.0]], dtype = np.float32).repeat(len(self.vertices), axis=0)
        else:
            # colors array is half the size of the connectivity array
            assert( len(self.vertices) == len(colors) )
            self.colors = colors

        # create pointers
        self.vertices_ptr = self.vertices.ctypes.data
        self.connectivity_ptr = self.connectivity.ctypes.data
        self.connectivity_nr = self.connectivity.size
        self.colors_ptr = self.colors.ctypes.data

    def draw(self):
        glPushMatrix()
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_COLOR_ARRAY)
        glVertexPointer(3, GL_FLOAT, 0, self.vertices_ptr)
        glColorPointer(4, GL_FLOAT, 0, self.colors_ptr)
        glDrawElements(GL_LINES, self.connectivity_nr, GL_UNSIGNED_INT, self.connectivity_ptr)
        glDisableClientState(GL_COLOR_ARRAY)
        glDisableClientState(GL_VERTEX_ARRAY)
        glPopMatrix()