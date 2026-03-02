package com.optiways

import android.app.Application
import dagger.hilt.android.HiltAndroidApp

@HiltAndroidApp
class OptiWaysApp : Application() {
    override fun onCreate() {
        super.onCreate()
    }
}
