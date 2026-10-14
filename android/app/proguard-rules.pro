# kotlinx.serialization: keep the generated serializers of the dashboard's JSON
# shapes (kit/Models.kt), which R8 cannot see being reached reflectively.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
-keepclassmembers @kotlinx.serialization.Serializable class com.daedalustcg.jfinances.** {
    *** Companion;
    kotlinx.serialization.KSerializer serializer(...);
}
-keepclasseswithmembers class com.daedalustcg.jfinances.** {
    kotlinx.serialization.KSerializer serializer(...);
}
-keep,includedescriptorclasses class com.daedalustcg.jfinances.**$$serializer { *; }
