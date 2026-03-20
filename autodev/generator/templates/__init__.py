"""Flutter project templates: registry mapping template names to file lists.

Each template defines an ordered list of files to generate, with their purpose
descriptions used as context for the Claude code generation prompt.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Shared file specs used across ALL templates
# ---------------------------------------------------------------------------

_COMMON_CONFIG_FILES: list[dict[str, str]] = [
    {
        "path": "pubspec.yaml",
        "purpose": (
            "Flutter project manifest. Include all dependencies from the PRD, "
            "flutter SDK constraint >=3.22.0, Dart SDK >=3.4.0. "
            "Include flutter_localizations under dependencies with sdk: flutter."
        ),
    },
    {
        "path": "analysis_options.yaml",
        "purpose": "Dart analysis options. Use flutter_lints recommended rules.",
    },
    {
        "path": "lib/config/ad_config.dart",
        "purpose": (
            "AdMob configuration: test ad unit IDs for banner ads "
            "(ca-app-pub-3940256099942544/6300978111 for Android, "
            "ca-app-pub-3940256099942544/2934735716 for iOS). "
            "Include a helper to get the correct ID per platform."
        ),
    },
    {
        "path": "lib/theme/app_theme.dart",
        "purpose": (
            "Material Design 3 theme definitions. Provide lightTheme and darkTheme "
            "using ColorScheme.fromSeed with useMaterial3: true. "
            "Include text theme customisations."
        ),
    },
    {
        "path": "lib/l10n/app_en.arb",
        "purpose": "English ARB localisation file with all user-facing strings.",
    },
    {
        "path": "lib/l10n/app_ja.arb",
        "purpose": "Japanese ARB localisation file with all user-facing strings.",
    },
    {
        "path": "lib/providers/theme_provider.dart",
        "purpose": (
            "Riverpod provider for theme mode (light/dark/system). "
            "Persist selection with shared_preferences."
        ),
    },
    {
        "path": "lib/providers/locale_provider.dart",
        "purpose": (
            "Riverpod provider for app locale (en/ja). "
            "Persist selection with shared_preferences."
        ),
    },
    {
        "path": "lib/router/app_router.dart",
        "purpose": (
            "GoRouter configuration with all routes defined in the PRD. "
            "Include a Riverpod provider for the router instance."
        ),
    },
    {
        "path": "lib/widgets/ad_banner_widget.dart",
        "purpose": (
            "Reusable AdMob banner widget using google_mobile_ads. "
            "Handle ad loading, errors, and dispose properly."
        ),
    },
]

_COMMON_ENTRY_FILES: list[dict[str, str]] = [
    {
        "path": "lib/main.dart",
        "purpose": (
            "App entry point. Initialise WidgetsBinding, MobileAds, "
            "then run the app wrapped in ProviderScope."
        ),
    },
    {
        "path": "lib/app.dart",
        "purpose": (
            "Root MaterialApp.router widget. Wire up GoRouter, theme, "
            "locale, and localisation delegates."
        ),
    },
]


def _make_template(extra_files: list[dict[str, str]]) -> dict[str, Any]:
    """Combine common files with template-specific files."""
    return {
        "files": _COMMON_CONFIG_FILES + extra_files + _COMMON_ENTRY_FILES,
    }


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

TEMPLATE_REGISTRY: dict[str, dict[str, Any]] = {
    "single_page_tool": _make_template([
        {
            "path": "lib/providers/tool_provider.dart",
            "purpose": "Riverpod provider for the tool's core state and logic.",
        },
        {
            "path": "lib/widgets/tool_input_widget.dart",
            "purpose": "Input widget for the tool (text fields, sliders, pickers, etc.).",
        },
        {
            "path": "lib/widgets/tool_result_widget.dart",
            "purpose": "Widget that displays the tool's output/result.",
        },
        {
            "path": "lib/screens/home_screen.dart",
            "purpose": (
                "Main (and only) screen. Contains the tool input, result display, "
                "and an AdMob banner at the bottom."
            ),
        },
        {
            "path": "lib/screens/settings_screen.dart",
            "purpose": "Settings screen with theme toggle and language selector.",
        },
    ]),

    "list_display": _make_template([
        {
            "path": "lib/models/item_model.dart",
            "purpose": "Data model for list items as defined in the PRD.",
        },
        {
            "path": "lib/services/item_service.dart",
            "purpose": "Service to load, save, and manage items (local storage).",
        },
        {
            "path": "lib/providers/item_provider.dart",
            "purpose": "Riverpod providers for item list, filtering, and search state.",
        },
        {
            "path": "lib/widgets/item_card.dart",
            "purpose": "Card widget for a single list item.",
        },
        {
            "path": "lib/widgets/search_bar_widget.dart",
            "purpose": "Search/filter bar widget.",
        },
        {
            "path": "lib/screens/list_screen.dart",
            "purpose": "Main list view with search, filtering, and AdMob banner.",
        },
        {
            "path": "lib/screens/detail_screen.dart",
            "purpose": "Detail view for a selected item.",
        },
        {
            "path": "lib/screens/add_edit_screen.dart",
            "purpose": "Form screen for adding or editing an item.",
        },
        {
            "path": "lib/screens/settings_screen.dart",
            "purpose": "Settings screen with theme toggle and language selector.",
        },
    ]),

    "timer": _make_template([
        {
            "path": "lib/models/timer_model.dart",
            "purpose": "Data model for timer/session state.",
        },
        {
            "path": "lib/services/timer_service.dart",
            "purpose": "Timer logic service handling countdown/stopwatch functionality.",
        },
        {
            "path": "lib/services/notification_service.dart",
            "purpose": "Local notification setup for timer completion alerts.",
        },
        {
            "path": "lib/providers/timer_provider.dart",
            "purpose": "Riverpod providers for timer state, controls, and history.",
        },
        {
            "path": "lib/widgets/timer_display.dart",
            "purpose": "Animated circular/digital timer display widget.",
        },
        {
            "path": "lib/widgets/timer_controls.dart",
            "purpose": "Start/pause/reset control buttons.",
        },
        {
            "path": "lib/screens/timer_screen.dart",
            "purpose": "Main timer screen with display, controls, and AdMob banner.",
        },
        {
            "path": "lib/screens/history_screen.dart",
            "purpose": "History of completed timer sessions.",
        },
        {
            "path": "lib/screens/settings_screen.dart",
            "purpose": "Settings: timer defaults, theme toggle, language selector.",
        },
    ]),

    "tracker": _make_template([
        {
            "path": "lib/models/entry_model.dart",
            "purpose": "Data model for tracked entries as defined in the PRD.",
        },
        {
            "path": "lib/services/storage_service.dart",
            "purpose": "Local storage service for persisting tracked entries.",
        },
        {
            "path": "lib/services/stats_service.dart",
            "purpose": "Statistics calculation service (averages, streaks, trends).",
        },
        {
            "path": "lib/providers/tracker_provider.dart",
            "purpose": "Riverpod providers for entries, stats, and filter state.",
        },
        {
            "path": "lib/widgets/entry_card.dart",
            "purpose": "Card widget for a single tracked entry.",
        },
        {
            "path": "lib/widgets/stats_chart.dart",
            "purpose": "Chart widget showing tracked data over time.",
        },
        {
            "path": "lib/widgets/quick_add_widget.dart",
            "purpose": "Quick-add floating action or inline widget for new entries.",
        },
        {
            "path": "lib/screens/dashboard_screen.dart",
            "purpose": "Main dashboard with today's summary, chart, and AdMob banner.",
        },
        {
            "path": "lib/screens/history_screen.dart",
            "purpose": "Full history list with filtering by date range.",
        },
        {
            "path": "lib/screens/add_entry_screen.dart",
            "purpose": "Form screen for adding/editing an entry.",
        },
        {
            "path": "lib/screens/settings_screen.dart",
            "purpose": "Settings screen with theme toggle and language selector.",
        },
    ]),

    "info_aggregator": _make_template([
        {
            "path": "lib/models/info_model.dart",
            "purpose": "Data model for information items/cards.",
        },
        {
            "path": "lib/services/api_service.dart",
            "purpose": "HTTP service for fetching data from external APIs or local sources.",
        },
        {
            "path": "lib/services/cache_service.dart",
            "purpose": "Local caching service for offline support.",
        },
        {
            "path": "lib/providers/info_provider.dart",
            "purpose": "Riverpod providers for data fetching, caching, and refresh state.",
        },
        {
            "path": "lib/widgets/info_card.dart",
            "purpose": "Card widget displaying a piece of aggregated information.",
        },
        {
            "path": "lib/widgets/loading_widget.dart",
            "purpose": "Shimmer/skeleton loading placeholder.",
        },
        {
            "path": "lib/screens/home_screen.dart",
            "purpose": "Main dashboard with aggregated info cards and AdMob banner.",
        },
        {
            "path": "lib/screens/detail_screen.dart",
            "purpose": "Detail view for a selected information item.",
        },
        {
            "path": "lib/screens/settings_screen.dart",
            "purpose": "Settings: data sources, refresh interval, theme, language.",
        },
    ]),

    "mini_game": _make_template([
        {
            "path": "lib/models/game_state.dart",
            "purpose": "Data model for game state, score, and progress.",
        },
        {
            "path": "lib/services/game_service.dart",
            "purpose": "Core game logic service.",
        },
        {
            "path": "lib/services/score_service.dart",
            "purpose": "High score persistence using local storage.",
        },
        {
            "path": "lib/providers/game_provider.dart",
            "purpose": "Riverpod providers for game state, score, and controls.",
        },
        {
            "path": "lib/widgets/game_board.dart",
            "purpose": "Main game board/canvas widget.",
        },
        {
            "path": "lib/widgets/score_display.dart",
            "purpose": "Score and game status display widget.",
        },
        {
            "path": "lib/screens/game_screen.dart",
            "purpose": "Main game screen with game board, score, and AdMob banner.",
        },
        {
            "path": "lib/screens/menu_screen.dart",
            "purpose": "Start menu with play, high scores, and settings buttons.",
        },
        {
            "path": "lib/screens/high_scores_screen.dart",
            "purpose": "High scores leaderboard screen.",
        },
        {
            "path": "lib/screens/settings_screen.dart",
            "purpose": "Settings: difficulty, theme toggle, language selector.",
        },
    ]),
}
