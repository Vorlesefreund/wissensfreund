import 'package:flutter/foundation.dart';

/// Coordinates visibility of the data-limit overlay.
/// The overlay lives in main.dart's _AppShell Stack.
class DataLimitOverlayService extends ChangeNotifier {
  DataLimitOverlayService._();
  static final instance = DataLimitOverlayService._();

  bool _visible = false;
  String _connectionType = 'wifi';
  VoidCallback? _onRetry;
  VoidCallback? _onCancel;

  bool   get isVisible       => _visible;
  String get connectionType  => _connectionType;

  void show({
    required VoidCallback onRetry,
    required VoidCallback onCancel,
    String connectionType = 'wifi',
  }) {
    _onRetry       = onRetry;
    _onCancel      = onCancel;
    _connectionType = connectionType;
    _visible       = true;
    notifyListeners();
  }

  void dismiss({bool retry = false}) {
    _visible = false;
    final cb = retry ? _onRetry : _onCancel;
    _onRetry  = null;
    _onCancel = null;
    notifyListeners();
    cb?.call();
  }
}
