# Install dependencies (none beyond stdlib!)
python3 ralph_loop.py

# Or customize inline
python3 -c "
from ralph_loop import RalphLoop, RalphConfig
loop = RalphLoop(RalphConfig(
    goal='Build a CLI tool for file encryption',
    max_iterations=3
))
loop.run()
"
