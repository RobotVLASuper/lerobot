#!/bin/bash 

#设置环境变量
export PYTHONBREAKPOINT=ipdb.set_trace
export CUDA_VISIBLE_DEVICES=0
export TOKENIZERS_PARALLELISM=false
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_DATASETS_OFFLINE=1

# 进入工作目录
rm -rf /data1/tmp/test_dataset/1

python -m lerobot.record \
    --display_data=False \
    --robot.type=ur5_follower \
    --robot.robot_ip="192.168.1.20" \
    --robot.with_gripper=True \
    --robot.cameras='{"0_top": {"type": "basler", "camera_idx": 0,}, "1_right": {"type": "basler", "camera_idx": 1}}' \
    --robot.max_relative_target=0.6 \
    --robot.init_pos_thr=0.3 \
    --robot.id=rjnj \
    --dataset.repo_id=rj/eval_record-test \
    --dataset.num_episodes=2 \
    --dataset.episode_time_s=300 \
    --dataset.root=/data1/tmp/test_dataset/1 \
    --dataset.single_task="Grasp a red insulator and hang it on teh hook." \
    --policy.path=/data1/workspace/huqiong/train_log/lerobot/smolvla/250627/2025-06-27/01-22-45_smolvla/checkpoints/200000/pretrained_model
    # --policy.n_action_steps= 20src/lerobot/model

    # <- Teleop optional if you want to teleoperate to record or in between episodes with a policy \
    # --teleop.port=/dev/tty.usbmodem58760431551 \
    # --teleop.type=ur_leader \
    # --teleop.grpc_host="192.168.1.111:50051" \
    # --teleop.id=rjnj

    # <- Policy optional if you want to record with a policy \
    # --policy.path=${HF_USER}/my_policy \

    #--policy.path=/data1/workspace/huqiong/train_log/lerobot/pi0/0701/2025-07-01/12-29-31_pi0/checkpoints/040000/pretrained_model 