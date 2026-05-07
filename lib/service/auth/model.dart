import 'package:json_annotation/json_annotation.dart';

part 'model.g.dart';

@JsonSerializable()
class UserModel {
  final String uid;
  final String? email;
  final String? displayName;
  final String? photoURL;
  final DateTime? subscriptionEndsAt;
  final Map<String, dynamic>? rawData;

  UserModel({
    required this.uid,
    this.email,
    this.displayName,
    this.photoURL,
    this.subscriptionEndsAt,
    this.rawData,
  });

  factory UserModel.fromMap(Map<String, dynamic> map, {String? uid}) {
    return UserModel(
      uid: uid ?? map['uid'] ?? map['id'] ?? '',
      email: map['email'],
      displayName: map['displayName'],
      photoURL: map['photoURL'],
      subscriptionEndsAt: map['subscriptionEndsAt'] != null 
          ? DateTime.tryParse(map['subscriptionEndsAt'])?.toLocal()
          : null,
      rawData: map,
    );
  }

  factory UserModel.fromJson(Map<String, dynamic> json) => _$UserModelFromJson(json);
  Map<String, dynamic> toJson() => _$UserModelToJson(this);

  bool get hasActiveSubscription {
    if (subscriptionEndsAt == null) return false;
    return subscriptionEndsAt!.isAfter(DateTime.now());
  }

  bool get isAppleLinked {
    return rawData?['externalApple'] != null;
  }

  bool get isTelegramLinked {
    return rawData?['externalTg'] != null;
  }

  bool get isVkLinked {
    return rawData?['externalVk'] != null;
  }

  List<String> get connectedSocials {
    final list = <String>[];
    if (isAppleLinked) list.add('apple');
    if (isTelegramLinked) list.add('telegram');
    if (isVkLinked) list.add('vk');
    return list;
  }
}
