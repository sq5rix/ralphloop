#!/usr/bin/env python3
"""
RALPH Loop - Recursive Autonomous LLM Heuristic Processing
Python implementation using Claude Code CLI subprocess calls
"""

import subprocess
import sys
import time
import shutil
import re
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class RalphConfig:
    goal: str = "Build a Python REST API with CRUD operations for a task manager"
    max_iterations: int = 5
    prd_file: Path = Path("prd_context.md")
    output_dir: Path = Path("ralph_output")
    log_file: Path = Path("ralph_loop.log")
    claude_model: str = "claude-opus-4-5"
    delay_between_iterations: int = 3
    allowed_tools: list[str] = field(default_factory=lambda: [
        "Edit", "Write", "Read", "Bash", "Glob", "Grep"
    ])


# =============================================================================
# LOGGING SETUP
# =============================================================================

def setup_logging(log_file: Path) -> logging.Logger:
    logger = logging.getLogger("ralph")
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )

    # Console handler with colors
    class ColorHandler(logging.StreamHandler):
        COLORS = {
            logging.DEBUG:    "\033[0;37m",   # White
            logging.INFO:     "\033[0;34m",   # Blue
            logging.WARNING:  "\033[1;33m",   # Yellow
            logging.ERROR:    "\033[0;31m",   # Red
            logging.CRITICAL: "\033[0;32m",   # Green
        }
        RESET = "\033[0m"

        def emit(self, record):
            color = self.COLORS.get(record.levelno, self.RESET)
            record.msg = f"{color}{record.msg}{self.RESET}"
            super().emit(record)

    console_handler = ColorHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(log_file, mode="w")
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


# =============================================================================
# PRD MANAGER
# =============================================================================

class PRDManager:
    """Manages the Product Requirements Document used as shared memory."""

    def __init__(self, prd_file: Path, goal: str, logger: logging.Logger):
        self.prd_file = prd_file
        self.goal = goal
        self.logger = logger

    def initialize(self) -> None:
        """Create the initial PRD for iteration 1."""
        content = f"""# PRD - Product Requirements Document
## Ralph Loop Context File

**Goal:** {self.goal}

**Iteration:** 1
**Status:** STARTING
**Last Updated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Objectives for This Iteration
- Analyze the goal and define the project structure
- Create a detailed implementation plan
- Identify key components and dependencies

## Constraints
- Use Python 3.10+
- Use FastAPI framework
- Include proper error handling
- Write clean, documented code

## Previous Iterations Summary
None - This is the first iteration.

## Expected Deliverables
- Project structure definition
- Initial code scaffold
- Dependencies list (requirements.txt)

## Success Criteria
- [ ] Project structure created
- [ ] Main entry point defined
- [ ] At least one CRUD endpoint implemented
- [ ] All tests passing
- [ ] Documentation written
"""
        self.prd_file.write_text(content, encoding="utf-8")
        self.logger.critical(f"PRD initialized: {self.prd_file}")

    def read(self) -> str:
        """Read current PRD content."""
        if not self.prd_file.exists():
            raise FileNotFoundError(f"PRD file not found: {self.prd_file}")
        return self.prd_file.read_text(encoding="utf-8")

    def get_current_iteration(self) -> int:
        """Extract current iteration number from PRD."""
        content = self.read()
        match = re.search(r"\*\*Iteration:\*\*\s*(\d+)", content)
        return int(match.group(1)) if match else 1

    def is_completed(self) -> bool:
        """Check if the goal has been marked as completed."""
        content = self.read()
        return bool(re.search(r"Status.*COMPLETED", content, re.IGNORECASE))

    def apply_fallback_update(self, iteration: int) -> None:
        """Update PRD if Claude forgot to do it."""
        current = self.get_current_iteration()
        if current <= iteration:
            self.logger.warning("Claude did not update PRD. Applying fallback...")
            content = self.read()
            content = content.replace(
                f"**Iteration:** {iteration}",
                f"**Iteration:** {iteration + 1}"
            )
            content += f"\n\n## Fallback Note\nIteration {iteration} completed. PRD auto-updated.\n"
            self.prd_file.write_text(content, encoding="utf-8")

    def save_snapshot(self, snapshot_dir: Path) -> None:
        """Save a copy of the current PRD as a snapshot."""
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(self.prd_file, snapshot_dir / "prd_snapshot.md")


# =============================================================================
# PROMPT BUILDER
# =============================================================================

class PromptBuilder:
    """Builds structured prompts for each Claude iteration."""

    def __init__(self, prd_file: Path):
        self.prd_file = prd_file

    def build(self, iteration: int, prd_content: str) -> str:
        return f"""You are an autonomous software engineer working on a project iteratively.

## Current PRD Context:
{prd_content}

## Your Task for Iteration {iteration}:
1. Read the PRD above carefully
2. Implement the objectives listed for this iteration
3. Create or update the necessary files in the project
4. After completing the work, update the file `{self.prd_file}` with:
   - Increment the iteration number
   - Update the status (IN_PROGRESS / COMPLETED / NEEDS_REVIEW)
   - Summarize what was accomplished in this iteration
   - Define clear objectives for the NEXT iteration
   - Update the success criteria checkboxes
   - Add any blockers or notes

## Important Rules:
- Always update the PRD file at the end of your work
- Be specific about what was done and what remains
- If the goal is fully achieved, set Status to COMPLETED
- Write production-quality code with comments

## Start working now on iteration {iteration}.
"""


# =============================================================================
# CLAUDE RUNNER
# =============================================================================

class ClaudeRunner:
    """Handles subprocess calls to the Claude Code CLI."""

    def __init__(self, config: RalphConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger

    def _check_claude_available(self) -> bool:
        """Verify that the claude CLI is installed."""
        return shutil.which("claude") is not None

    def run(self, prompt: str, iteration: int) -> tuple[bool, str]:
        """
        Run Claude Code with a fresh context (no memory of previous sessions).
        Returns (success: bool, output: str)
        """
        if not self._check_claude_available():
            self.logger.error("Claude CLI not found. Please install it first.")
            return False, ""

        cmd = [
            "claude",
            "--model", self.config.claude_model,
            "-p",                          # Non-interactive / fresh session
            "--allowedTools", ",".join(self.config.allowed_tools),
            "--output-format", "text",
        ]

        self.logger.info(f"Launching Claude Code (iteration {iteration}, fresh context)...")

        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=300,               # 5 min timeout per iteration
                encoding="utf-8"
            )

            output = result.stdout + result.stderr

            if result.returncode == 0:
                self.logger.critical(f"Claude completed iteration {iteration} successfully")
                return True, output
            else:
                self.logger.error(
                    f"Claude exited with code {result.returncode} "
                    f"on iteration {iteration}"
                )
                return False, output

        except subprocess.TimeoutExpired:
            self.logger.error(f"Claude timed out on iteration {iteration}")
            return False, "TIMEOUT"

        except Exception as e:
            self.logger.error(f"Unexpected error running Claude: {e}")
            return False, str(e)


# =============================================================================
# RALPH LOOP ORCHESTRATOR
# =============================================================================

class RalphLoop:
    """Main orchestrator for the Ralph Loop."""

    def __init__(self, config: RalphConfig):
        self.config = config
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

        self.logger = setup_logging(config.log_file)
        self.prd_manager = PRDManager(config.prd_file, config.goal, self.logger)
        self.prompt_builder = PromptBuilder(config.prd_file)
        self.claude_runner = ClaudeRunner(config, self.logger)

    def _print_banner(self) -> None:
        self.logger.info("=" * 50)
        self.logger.info("  RALPH LOOP - Starting")
        self.logger.info(f"  Goal: {self.config.goal}")
        self.logger.info(f"  Max Iterations: {self.config.max_iterations}")
        self.logger.info("=" * 50)

    def _save_iteration_output(self, iteration: int, output: str) -> None:
        """Save Claude's raw output for this iteration."""
        output_file = self.config.output_dir / f"iter_{iteration}_output.txt"
        output_file.write_text(output, encoding="utf-8")

    def run(self) -> None:
        """Execute the full Ralph Loop."""
        self._print_banner()
        self.prd_manager.initialize()

        for iteration in range(1, self.config.max_iterations + 1):
            self.logger.info("")
            self.logger.info("=" * 50)
            self.logger.info(f"  ITERATION {iteration} / {self.config.max_iterations}")
            self.logger.info("=" * 50)

            # Save snapshot before running
            snapshot_dir = self.config.output_dir / "snapshots" / f"iter_{iteration}"
            self.prd_manager.save_snapshot(snapshot_dir)

            # Build prompt from current PRD
            prd_content = self.prd_manager.read()
            prompt = self.prompt_builder.build(iteration, prd_content)

            # Run Claude with fresh context
            success, output = self.claude_runner.run(prompt, iteration)
            self._save_iteration_output(iteration, output)

            # Fallback PRD update if Claude didn't do it
            self.prd_manager.apply_fallback_update(iteration)

            # Check completion
            if self.prd_manager.is_completed():
                self.logger.critical("=" * 50)
                self.logger.critical(f"  GOAL ACHIEVED after {iteration} iterations!")
                self.logger.critical("=" * 50)
                break

            if iteration < self.config.max_iterations:
                self.logger.info(
                    f"Waiting {self.config.delay_between_iterations}s "
                    f"before next iteration..."
                )
                time.sleep(self.config.delay_between_iterations)

        # Final summary
        self.logger.info("")
        self.logger.info("=" * 50)
        self.logger.info("  RALPH LOOP - Final PRD State")
        self.logger.info("=" * 50)
        print(self.prd_manager.read())
        self.logger.critical(f"Outputs saved in: {self.config.output_dir}")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    config = RalphConfig(
        goal="Build a Python REST API with CRUD operations for a task manager",
        max_iterations=5,
        claude_model="claude-opus-4-5",
        delay_between_iterations=3,
    )

    loop = RalphLoop(config)
    loop.run()

