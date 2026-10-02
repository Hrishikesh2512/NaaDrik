# MediaPipe Tasks reaches its graph and option classes through JNI and protobuf reflection.
-keep class com.google.mediapipe.** { *; }
-keep class com.google.protobuf.** { *; }
-dontwarn com.google.mediapipe.**
-dontwarn com.google.protobuf.**

# LiteRT (TensorFlow Lite) and its GPU delegate are bound from native code.
-keep class org.tensorflow.lite.** { *; }
-dontwarn org.tensorflow.lite.**

# AutoValue and annotation-only dependencies referenced by MediaPipe.
-dontwarn com.google.auto.value.**
-dontwarn javax.annotation.**
