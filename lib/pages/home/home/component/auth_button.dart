import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

class HomeAuthButton extends StatelessWidget {
  final dynamic icon;
  final LinearGradient gradient;
  final Color glowColor;
  final String title;
  final VoidCallback onTap;
  final bool isHighlighted;
  final bool isLoading;
  final bool isEnabled;

  const HomeAuthButton({
    super.key,
    required this.icon,
    required this.gradient,
    required this.glowColor,
    required this.title,
    required this.onTap,
    this.isHighlighted = false,
    this.isLoading = false,
    this.isEnabled = true,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: (isLoading || !isEnabled) ? null : onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 600),
        curve: Curves.easeInOut,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(20),
          color: Colors.white.withOpacity(0.04),
          border: Border.all(
            color: isHighlighted ? glowColor.withOpacity(0.7) : Colors.white.withOpacity(0.08),
            width: 1.5,
          ),
          boxShadow: isHighlighted
              ? [BoxShadow(color: glowColor.withOpacity(0.4), blurRadius: 24, spreadRadius: 4)]
              : [BoxShadow(color: Colors.black.withOpacity(0.3), blurRadius: 8)],
        ),
        child: Row(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                gradient: gradient,
                borderRadius: BorderRadius.circular(12),
                boxShadow: [BoxShadow(color: glowColor.withOpacity(0.3), blurRadius: 8)],
              ),
              alignment: Alignment.center,
              child: FaIcon(icon, color: Colors.white, size: 22),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Text(
                title,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.2,
                ),
              ),
            ),
            isLoading
                ? SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      valueColor: AlwaysStoppedAnimation<Color>(glowColor),
                    ),
                  )
                : Icon(
                    Icons.arrow_forward_ios_rounded,
                    color: Colors.white.withOpacity(0.3),
                    size: 16,
                  ),
          ],
        ),
      ),
    );
  }
}
