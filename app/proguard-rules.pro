# Room, Compose and Navigation ship their own consumer rules.
# Keep @Serializable navigation route classes (used by type-safe Navigation Compose).
-keepclassmembers @kotlinx.serialization.Serializable class com.endless.liftlog.** {
    *** Companion;
    kotlinx.serialization.KSerializer serializer(...);
}
-keep,includedescriptorclasses class com.endless.liftlog.**$$serializer { *; }
