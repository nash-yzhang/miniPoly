import os, shutil

local_dir = 'C:/Users/yue.zhang/PycharmProjects/miniPoly/apps/CaImg_App/data/20230718_113146'
remote_dir = '\\\\nas3\datastore_bonhoeffer_group$\Yue Zhang\CaData'

shutil.copytree(local_dir, os.path.join(remote_dir, os.path.basename(local_dir)))