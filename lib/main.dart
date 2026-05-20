import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'providers/wissensfreund_provider.dart';
import 'screens/home_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(
    ChangeNotifierProvider(
      create: (_) => WissensfreundProvider(),
      child: const WissensfreundApp(),
    ),
  );
}

class WissensfreundApp extends StatelessWidget {
  const WissensfreundApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Wissensfreund',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF4CAF50),
          brightness: Brightness.light,
        ),
        useMaterial3: true,
      ),
      home: const HomeScreen(),
    );
  }
}
