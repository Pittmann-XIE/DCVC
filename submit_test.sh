#!/bin/bash
#SBATCH --job-name=dcvc_test
#SBATCH --output=slurm_dcvc_%j.out
#SBATCH --error=slurm_dcvc_%j.err
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=64G
#SBATCH --time=24:00:00

set -eo pipefail

echo "Job running on node: $SLURM_JOB_NODELIST"
echo "Starting DCVC test..."
echo "Submitted from: $SLURM_SUBMIT_DIR"

source ~/.bashrc
conda activate python312t

set -u

cd /home/fe/xie/video4robot/DCVC

# Make the compiled DCVC extension use conda's newer libstdc++ instead of /lib64.
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:${LD_LIBRARY_PATH:-}"
export LD_PRELOAD="$CONDA_PREFIX/lib/libstdc++.so.6${LD_PRELOAD:+:$LD_PRELOAD}"

echo "Python: $(which python)"
python -c "import torch; print('torch:', torch.__version__); print('cuda available:', torch.cuda.is_available()); print('gpu count:', torch.cuda.device_count())"
python -c "import sys; sys.path.insert(0, './src/cpp'); import MLCodec_extensions_cpp; print('DCVC C++ extension: ok')"

python -u test_video.py \
    --model_path_i ./checkpoints/cvpr2025_image.pth.tar \
    --model_path_p ./checkpoints/cvpr2025_video.pth.tar \
    --rate_num 4 \
    --test_config ./custom_config_yuv420.json \
    --cuda 1 \
    -w 1 \
    --write_stream 1 \
    --save_decoded_frame 1 \
    --force_zero_thres 0.12 \
    --output_path output.json \
    --force_intra_period -1 \
    --reset_interval 64 \
    --force_frame_num 32 \
    --check_existing 0 \
    --verbose 2

echo "DCVC test finished."
