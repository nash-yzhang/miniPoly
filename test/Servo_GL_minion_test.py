from APP.GL_test.GL_test_app import GLapp
import os

if __name__ == "__main__":
    os.chdir('APP/GL_test')
    app = GLapp("main")
    app.run()