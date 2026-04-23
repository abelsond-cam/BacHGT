#!/bin/bash
#SBATCH --job-name=gpa_dist_combined    
#SBATCH --output=gpa_dist_combined_%j.out     
#SBATCH --error=gpa_dist_combined_%j.err
#SBATCH --partition=icelake
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=76
#SBATCH --time=02:30:00
#SBATCH --account=FLOTO-PROJECT-K-SL2-CPU  

cd /home/dca36/workspace/Bacotype

# Force Python unbuffered output for real-time logging
export PYTHONUNBUFFERED=1

echo "========================================================================"
echo "Starting GPA distances combined analysis - every Panaroo run's detail TSV is analysed"
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURMD_NODENAME"
echo "CPUs: $SLURM_CPUS_PER_TASK"
echo "========================================================================"
echo ""

# ESM embeddings
# uv run python src/bacotype/pp/prepare_esmc_embeddings_and_labels_to_finetune_amr.py --skip-existing
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] About to start: uv run python src/bacotype/tl/gpa_distances_combined.py --mode combined"
uv run python src/bacotype/tl/gpa_distances_combined.py --mode combined

echo ""
echo "========================================================================"
echo "Processing complete!"
echo "========================================================================"

# Run with: sbatch cpu_slurm.sh
# Check on progress with: squeue -u dca36
# To cancel: scancel jobid

