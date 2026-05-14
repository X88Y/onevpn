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
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          color: Colors.white.withOpacity(0.03),
          border: Border.all(
            color: isHighlighted ? glowColor.withOpacity(0.8) : Colors.white.withOpacity(0.06),
            width: 1.2,
          ),
          boxShadow: isHighlighted
              ? [
                  BoxShadow(color: glowColor.withOpacity(0.3), blurRadius: 20, spreadRadius: 2),
                  BoxShadow(color: glowColor.withOpacity(0.1), blurRadius: 40, spreadRadius: 8),
                ]
              : [BoxShadow(color: Colors.black.withOpacity(0.3), blurRadius: 8)],
        ),
        child: Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                gradient: gradient,
                borderRadius: BorderRadius.circular(10),
                boxShadow: [
                  BoxShadow(color: glowColor.withOpacity(0.4), blurRadius: 10, spreadRadius: 1),
                ],
              ),
              alignment: Alignment.center,
              child: FaIcon(icon, color: Colors.white, size: 20),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 0.2,
                      height: 1.2,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Container(
                    width: 24,
                    height: 2,
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        colors: [glowColor.withOpacity(0.8), Colors.transparent],
                      ),
                      borderRadius: BorderRadius.circular(1),
                    ),
                  ),
                ],
              ),
            ),
            isLoading
                ? SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      valueColor: AlwaysStoppedAnimation<Color>(glowColor),
                    ),
                  )
                : Container(
                    width: 28,
                    height: 28,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: glowColor.withOpacity(0.1),
                      border: Border.all(color: glowColor.withOpacity(0.3), width: 1),
                    ),
                    child: Icon(
                      Icons.arrow_forward_rounded,
                      color: glowColor.withOpacity(0.8),
                      size: 14,
                    ),
                  ),
          ],
        ),
      ),
    );
  }
}
