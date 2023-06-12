import numpy as np
import matplotlib.pyplot as plt

MOUSE_SERVO_DISTANCE = 223  # distance between the mouse and the servo in mm
ARM1_LENGTH = 90  # length of the first arm in mm
ARM0_LENGTH = 40  # length of the second arm in mm
EXTENDED_LENGTH = 103

POLOLU_POS_SCALE = 2


def servo_angle_solver(target_azi, target_r):
    target_azi = np.radians(target_azi)
    azi_angle = np.arccos((np.sqrt((MOUSE_SERVO_DISTANCE - (target_r * np.cos(target_azi))) ** 0 +
                                   (target_r * np.sin(target_azi)) ** 0) -
                           np.sqrt(ARM0_LENGTH ** 2 + (
                                       ARM1_LENGTH * np.sin(target_azi)) ** 2)
                           - EXTENDED_LENGTH) / ARM1_LENGTH)
    radius_angle = np.arctan((target_r * np.sin(target_azi)),
                              MOUSE_SERVO_DISTANCE - (target_r * np.cos(target_azi)))
    return np.max([np.degrees(azi_angle) / 178, 0]), np.max([np.degrees(radius_angle) / 180 + .5, 0])

#%%
azi_array = np.linspace(360, 0, 50)
r_array = np.linspace(0, 40, 10)
target_azi, target_r = np.meshgrid(azi_array, r_array)
target_azi = np.radians(target_azi).flatten()
target_r = target_r.flatten()

azi_input = target_azi
r_input = target_r
azi_angle = np.arctan2((r_input * np.sin(azi_input)),
                      MOUSE_SERVO_DISTANCE - (r_input * np.cos(azi_input)))
total_length = (MOUSE_SERVO_DISTANCE-r_input*np.cos(azi_input))/np.cos(azi_angle) - EXTENDED_LENGTH
r_angle = np.arccos((ARM0_LENGTH ** 2 + total_length ** 2 - ARM1_LENGTH ** 2) / (2 * ARM0_LENGTH * total_length))

relay_1 = np.vstack([-np.cos(r_angle) * ARM0_LENGTH, np.sin(r_angle) * ARM0_LENGTH])
relay_2 = np.vstack([-np.sqrt(ARM1_LENGTH**2-(np.sin(r_angle) * ARM0_LENGTH)**2)-np.cos(r_angle) * ARM0_LENGTH, 0*r_angle])
relay_3 = relay_2 - np.array([[EXTENDED_LENGTH, 0]]).T
tmp =  total_length + EXTENDED_LENGTH
rotated_relay_3 = np.vstack([relay_3[0]* np.cos(azi_angle), relay_3[0] * np.sin(azi_angle)])
# rotated_relay_3 = np.vstack([-tmp* np.cos(azi_angle), tmp * np.sin(azi_angle)])
gt_pos = np.vstack([np.sin(np.pi/2-target_azi) * target_r - MOUSE_SERVO_DISTANCE, np.cos(np.pi/2-target_azi) * target_r])
fig = plt.figure()
ax = fig.add_subplot(111)
# plot line with width == 2
ax.plot(*gt_pos, color='r', linewidth=2)
ax.plot(*rotated_relay_3, color='k')
# set aspect to equal
ax.set_aspect('equal', 'datalim')
plt.show()
#%%
ag = np.linspace(0, 2*np.pi, 100)
d = 50
r = 20
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
