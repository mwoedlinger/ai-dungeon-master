"""Interactive terminal screens (Layer 3a of the inventory/character redesign).

Keyboard-driven modal menus that sit on top of the transport-agnostic
``InventoryController``. The View never mutates state — it calls the controller
and re-renders. See ``docs/DESIGN_INVENTORY_UI.md``.
"""
from src.interface.screens.character_screen import run_character_screen
from src.interface.screens.inventory_screen import run_inventory_screen
from src.interface.screens.menu import MenuOption, interactive_enabled, select

__all__ = [
    "MenuOption",
    "interactive_enabled",
    "run_character_screen",
    "run_inventory_screen",
    "select",
]
