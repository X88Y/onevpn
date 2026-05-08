import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

class SocialBubble extends StatelessWidget {
  final dynamic icon;
  final Color glowColor;
  final VoidCallback onTap;
  final bool isHighlighted;
  final bool isLoading;
  final bool isEnabled;

  const SocialBubble({
    super.key,
    required this.icon,
    required this.glowColor,
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
        width: 46,
        height: 46,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: isHighlighted ? glowColor.withOpacity(0.2) : Colors.white.withOpacity(0.08),
          border: Border.all(
            color: isHighlighted ? glowColor.withOpacity(0.8) : Colors.white.withOpacity(0.15),
            width: 1.5,
          ),
          boxShadow: [
            BoxShadow(
              color: glowColor.withOpacity(isHighlighted ? 0.5 : 0.2),
              blurRadius: isHighlighted ? 20 : 10,
              spreadRadius: isHighlighted ? 3 : 0,
            ),
          ],
        ),
        alignment: Alignment.center,
        child: isLoading
            ? SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  valueColor: AlwaysStoppedAnimation<Color>(glowColor),
                ),
              )
            : FaIcon(icon, color: Colors.white, size: 20),
      ),
    );
  }
}
