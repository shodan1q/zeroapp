import 'dart:async';

import 'package:flutter/material.dart';

void main() => runApp(const PomodoroApp());

class PomodoroApp extends StatelessWidget {
  const PomodoroApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Pomodoro Timer',
      themeMode: ThemeMode.system,
      theme: ThemeData(
        colorSchemeSeed: Colors.red,
        useMaterial3: true,
        brightness: Brightness.light,
      ),
      darkTheme: ThemeData(
        colorSchemeSeed: Colors.red,
        useMaterial3: true,
        brightness: Brightness.dark,
      ),
      home: const PomodoroScreen(),
    );
  }
}

enum TimerPhase { work, rest }

class PomodoroScreen extends StatefulWidget {
  const PomodoroScreen({super.key});

  @override
  State<PomodoroScreen> createState() => _PomodoroScreenState();
}

class _PomodoroScreenState extends State<PomodoroScreen> {
  static const int workDuration = 25 * 60;
  static const int breakDuration = 5 * 60;

  TimerPhase _phase = TimerPhase.work;
  int _secondsRemaining = workDuration;
  bool _isRunning = false;
  Timer? _timer;

  void _start() {
    if (_isRunning) return;
    setState(() => _isRunning = true);
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      setState(() {
        if (_secondsRemaining > 0) {
          _secondsRemaining--;
        } else {
          _switchPhase();
        }
      });
    });
  }

  void _pause() {
    _timer?.cancel();
    setState(() => _isRunning = false);
  }

  void _reset() {
    _timer?.cancel();
    setState(() {
      _isRunning = false;
      _secondsRemaining = _phase == TimerPhase.work ? workDuration : breakDuration;
    });
  }

  void _switchPhase() {
    _timer?.cancel();
    setState(() {
      _phase = _phase == TimerPhase.work ? TimerPhase.rest : TimerPhase.work;
      _secondsRemaining = _phase == TimerPhase.work ? workDuration : breakDuration;
      _isRunning = false;
    });
  }

  String get _timeDisplay {
    final m = (_secondsRemaining ~/ 60).toString().padLeft(2, '0');
    final s = (_secondsRemaining % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  double get _progress {
    final total = _phase == TimerPhase.work ? workDuration : breakDuration;
    return 1.0 - (_secondsRemaining / total);
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final isWork = _phase == TimerPhase.work;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Pomodoro Timer'),
        centerTitle: true,
      ),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            FilledButton.tonal(
              onPressed: null,
              child: Text(isWork ? 'WORK' : 'BREAK'),
            ),
            const SizedBox(height: 32),
            SizedBox(
              width: 220,
              height: 220,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  SizedBox(
                    width: 220,
                    height: 220,
                    child: CircularProgressIndicator(
                      value: _progress,
                      strokeWidth: 8,
                      backgroundColor: colorScheme.surfaceContainerHighest,
                      color: isWork ? colorScheme.primary : colorScheme.tertiary,
                    ),
                  ),
                  Text(
                    _timeDisplay,
                    style: Theme.of(context).textTheme.displayLarge?.copyWith(
                          fontFeatures: [const FontFeature.tabularFigures()],
                        ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 48),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                if (!_isRunning)
                  FilledButton.icon(
                    onPressed: _start,
                    icon: const Icon(Icons.play_arrow),
                    label: const Text('Start'),
                  )
                else
                  FilledButton.icon(
                    onPressed: _pause,
                    icon: const Icon(Icons.pause),
                    label: const Text('Pause'),
                  ),
                const SizedBox(width: 16),
                OutlinedButton.icon(
                  onPressed: _reset,
                  icon: const Icon(Icons.replay),
                  label: const Text('Reset'),
                ),
              ],
            ),
            const SizedBox(height: 16),
            TextButton(
              onPressed: _switchPhase,
              child: Text(isWork ? 'Skip to Break' : 'Skip to Work'),
            ),
          ],
        ),
      ),
    );
  }
}