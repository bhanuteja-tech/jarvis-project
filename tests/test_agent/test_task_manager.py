"""Tests for TaskManager: task creation, generation invalidation, and cancellation tokens."""

from app.agent.task_manager import TaskManager


def test_task_creation():
    tm = TaskManager()
    task = tm.create_task(intent="OPEN_APPLICATION", total_steps=2)
    assert task.task_id.startswith("task_")
    assert task.status == "pending"
    assert task.generation == 1
    assert task.total_steps == 2
    assert not task.is_cancelled()


def test_task_cancellation():
    tm = TaskManager()
    task = tm.create_task(intent="OPEN_APPLICATION")
    assert not task.is_cancelled()

    task.cancel()
    assert task.is_cancelled()
    assert task.status == "cancelled"
    assert task.cancellation_event.is_set()


def test_generation_invalidation():
    tm = TaskManager()
    gen1 = tm.current_generation
    task1 = tm.create_task(intent="STEP_1")
    assert tm.is_generation_valid(gen1)

    # Invalidate gen1 (e.g. on user correction or barge-in)
    tm.invalidate_generation(gen1)
    assert not tm.is_generation_valid(gen1)
    assert task1.is_cancelled()

    # Move to gen2
    gen2 = tm.next_generation()
    assert gen2 == 2
    assert tm.is_generation_valid(gen2)
    task2 = tm.create_task(intent="STEP_2")
    assert not task2.is_cancelled()
