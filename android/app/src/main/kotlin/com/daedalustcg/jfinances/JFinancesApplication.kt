package com.daedalustcg.jfinances

import android.app.Application
import com.daedalustcg.jfinances.app.AppModel
import com.daedalustcg.jfinances.kit.storage.Kit

class JFinancesApplication : Application() {
    /** The one app model, for the activity; widgets read the kit directly. */
    val model: AppModel by lazy { AppModel(this) }

    override fun onCreate() {
        super.onCreate()
        Kit.init(this)
    }
}
