import os, time, pwinput
import paramiko

ssh = paramiko.SSHClient()
ssh.load_system_host_keys()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
password = pwinput.pwinput('Enter password for remote directory: ')
ssh.connect('192.168.233.66', username='yue.zhang', password=password)
remote_dir = 'D:\\data\\'
fn = 'exp27754_ch-525.bin'
netdrive_dir = "\\\\nas3\\datastore_bonhoeffer_group$"
net_dir = netdrive_dir+'\\Yue Zhang\\CaData\\'
_, stdout, _ = ssh.exec_command(f'net use \"{netdrive_dir}\"')
print(stdout.channel.recv(1000).decode('utf-8'))
# #%%
# _, stout, sterr = ssh.exec_command(f"if exist \"{os.path.join(remote_dir, fn)}\" echo TRUE")
# if sterr.channel.recv_exit_status() != 0:
#     print(sterr.channel.recv_stderr(1000).decode('utf-8'))
# else:
#     print(stout.channel.recv(1000).decode('utf-8'))
#%%
t = time.time()
_, stout, sterr = ssh.exec_command(f"copy \"{os.path.join(remote_dir, fn)}\" \"{net_dir + 'CR_' + fn}\"")
if sterr.channel.recv_exit_status() != 0:
    print(sterr.channel.recv_stderr(1000).decode('utf-8'))
else:
    print(stout.channel.recv(1000).decode('utf-8'))
print(f"Time elapsed: {time.time()-t:.2f}s")
# %%
# t = time.time()
# remote_sftp = ssh.open_sftp()
# remote_sftp.get(os.path.join(remote_dir, fn), )
# print(f"Time elapsed: {time.time()-t:.2f}s")
# remote_sftp.close()
ssh.close()
# %%
