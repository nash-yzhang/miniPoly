import numpy as np
import matplotlib.pyplot as plt

MOUSE_SERVO_DISTANCE = 200  # distance between the mouse and the servo in mm
ARM1_LENGTH = 90  # length of the first arm in mm
ARM0_LENGTH = 40  # length of the second arm in mm
EXTENDED_LENGTH = 103

POLOLU_POS_SCALE = 2


def servo_angle_solver(target_azi, target_r):
    target_azi *= np.pi / 180
    target_azi -= np.pi / 2
    servo_azi = np.arctan2((target_r * np.sin(target_azi)),
                           MOUSE_SERVO_DISTANCE - (target_r * np.cos(target_azi)))
    total_length = (MOUSE_SERVO_DISTANCE - target_r * np.cos(target_azi)) / np.cos(servo_azi) - EXTENDED_LENGTH
    servo_r = np.arccos((ARM0_LENGTH ** 2 + total_length ** 2 - ARM1_LENGTH ** 2) / (2 * ARM0_LENGTH * total_length))
    return servo_azi, servo_r

#%%
total_length = 190
m_r = 30
s_arm2 = 95
s_arm0 = 40
s_arm1 = 90

s_ori = np.array([[0., 0.]]).T
m_ori = np.array([[0., total_length]]).T
mid_pos = []
end_pos = []
tar_pos = []
for target_azi in np.linspace(np.pi, np.pi*2, 20):
    m_pos = m_ori + m_r*np.vstack([np.cos(target_azi), np.sin(target_azi)])
    s_azi = np.pi/2-np.arctan(np.cos(target_azi)/(total_length/m_r+np.sin(target_azi)))
    s_r = (total_length + m_r * np.sin(target_azi))/np.sin(s_azi)
    s_arm_l = s_r - s_arm2
    s_r_ang = np.arccos((s_arm0 ** 2 + s_arm_l ** 2 - s_arm1 ** 2) / (2 * s_arm0 * s_arm_l))-np.pi/2
    s_r1_ang = np.arcsin(s_arm0*np.sin(np.pi/2-s_r_ang)/s_arm1)-np.pi/2
    print(f"Azi: {s_azi/np.pi*180}; r_angle: {s_r_ang/np.pi*180};")
    # s_r_ang = -np.pi/2+s_r_ang
    # s_r1_ang = -np.pi/2+s_r1_ang
    s_r_series = s_ori.repeat(4,axis=1).T
    s_r_series[1,:] = np.array([np.sin(-s_r_ang)*s_arm0,np.cos(-s_r_ang)*s_arm0,])
    s_r_series[2,:] = [np.sin(-s_r1_ang)*s_arm1,-np.cos(-s_r1_ang)*s_arm1,]
    s_r_series[3,:] = [s_arm2,0,]
    s_r_series = np.cumsum(s_r_series, axis=0).T
    # rotate s_r_series by s_azi
    s_azi_rot_mat = np.array([[np.cos(s_azi), -np.sin(s_azi)], [np.sin(s_azi), np.cos(s_azi)]])
    s_r_series = s_azi_rot_mat.dot(s_r_series)
    s_line_base = np.linspace(0,s_arm_l, 3)
    s_line = s_ori + np.vstack([np.cos(s_azi)*s_line_base, np.sin(s_azi)*s_line_base])
    tar_pos.append(m_pos.T)
    end_pos.append(s_r_series[:,-2])
    mid_pos.append(s_line[:,-1])
    s_line_base = np.linspace(0,s_r, 3)
    s_line = s_ori + np.vstack([np.cos(s_azi)*s_line_base, np.sin(s_azi)*s_line_base])
    # end_pos.append(s_line[:,-1])

    plt.clf()
    plt.plot(*s_ori, 'ro')
    plt.plot(*m_ori, 'bo')
    plt.plot(*s_line, 'k')
    plt.plot(*s_r_series, 'ro-')
    plt.plot(*m_pos, 'go')
    plt.plot(*np.array(tar_pos).T, 'go')
    # plt.plot(*np.array(mid_pos).T, 'b.')
    # plt.plot(*np.array(end_pos).T, 'r.')
    # plt.gca().set_xlim([-5, 5])
    plt.gca().set_aspect('equal')
    plt.draw()
    plt.show()
    plt.pause(0.01)
#%%
total_length = 3
s_arm2 = 1.5
s_arm0 = .5
s_arm1 = 1

m_angle = np.pi/3
m_r = 1

s_ori = 0+0j
m_ori = 0+total_length*1j
tar_pos = m_ori + np.exp(1j*m_angle)*m_r

s_R = np.abs(tar_pos-m_ori)
s_azi = np.angle(tar_pos-m_ori)
s_r12_l = s_R-s_arm2
# s_r1 =


#%%
ag = np.linspace(0, 2*np.pi, 100)
d = 20
r = 25
rd = -50
plt.figure(1)
plt.clf()
x = r*np.cos(ag)[...,None]+d*np.sin(ag)[...,None]*np.array([[1,0]])
y = r*np.sin(ag)[...,None]-d*np.cos(ag)[...,None]*np.array([[1,0]])
plt.plot(x.T,y.T, 'b')
plt.plot(x[:,0],y[:,0], 'k')
plt.plot(x[:,1],y[:,1], 'r')
plt.plot(x[:,0]+rd,y[:,0], 'cyan')
plt.gca().set_aspect('equal')
plt.draw()
plt.show()
