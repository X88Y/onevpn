// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'model.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

UserModel _$UserModelFromJson(Map<String, dynamic> json) => UserModel(
  uid: json['uid'] as String,
  email: json['email'] as String?,
  displayName: json['displayName'] as String?,
  photoURL: json['photoURL'] as String?,
  subscriptionEndsAt: json['subscriptionEndsAt'] == null
      ? null
      : DateTime.parse(json['subscriptionEndsAt'] as String),
  rawData: json['rawData'] as Map<String, dynamic>?,
);

Map<String, dynamic> _$UserModelToJson(UserModel instance) => <String, dynamic>{
  'uid': instance.uid,
  'email': instance.email,
  'displayName': instance.displayName,
  'photoURL': instance.photoURL,
  'subscriptionEndsAt': instance.subscriptionEndsAt?.toIso8601String(),
  'rawData': instance.rawData,
};
