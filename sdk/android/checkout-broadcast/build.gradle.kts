plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
    id("maven-publish")
}

android {
    namespace = "com.checkoutbroadcast"
    compileSdk = 34

    defaultConfig {
        minSdk = 26
        consumerProguardFiles("consumer-rules.pro")
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("org.jetbrains.kotlin:kotlin-stdlib:1.9.22")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}

// Publish to Maven Local: ./gradlew publishToMavenLocal
// Maven Central: configure OSSRH credentials (see docs/publishing.md)
publishing {
    publications {
        create<MavenPublication>("release") {
            groupId = "com.checkoutbroadcast"
            artifactId = "checkout-broadcast"
            version = "1.0.0"

            afterEvaluate {
                from(components["release"])
            }

            pom {
                name.set("Checkout Broadcast Android SDK")
                description.set("Receive signed POS checkout broadcasts in Android banking apps")
                url.set("https://github.com/checkout-broadcast/checkout-broadcast")
                licenses {
                    license {
                        name.set("MIT License")
                        url.set("https://opensource.org/licenses/MIT")
                    }
                }
                scm {
                    connection.set("scm:git:git://github.com/checkout-broadcast/checkout-broadcast.git")
                    developerConnection.set("scm:git:ssh://github.com/checkout-broadcast/checkout-broadcast.git")
                    url.set("https://github.com/checkout-broadcast/checkout-broadcast")
                }
            }
        }
    }
}
