package com.optiways.data.local

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.*
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "optiways_prefs")

@Singleton
class PreferencesDataStore @Inject constructor(
    @ApplicationContext private val context: Context
) {
    companion object {
        val COMMUTER_PROFILE = stringPreferencesKey("commuter_profile")
        val IS_DARK_MODE = booleanPreferencesKey("is_dark_mode")
        val LAST_KNOWN_LAT = floatPreferencesKey("last_known_lat")
        val LAST_KNOWN_LNG = floatPreferencesKey("last_known_lng")
    }

    val commuterProfile: Flow<String> = context.dataStore.data
        .catch { emit(emptyPreferences()) }
        .map { prefs -> prefs[COMMUTER_PROFILE] ?: "default" }

    val isDarkMode: Flow<Boolean> = context.dataStore.data
        .catch { emit(emptyPreferences()) }
        .map { prefs -> prefs[IS_DARK_MODE] ?: false }

    suspend fun setCommuterProfile(profile: String) {
        context.dataStore.edit { prefs -> prefs[COMMUTER_PROFILE] = profile }
    }

    suspend fun setDarkMode(enabled: Boolean) {
        context.dataStore.edit { prefs -> prefs[IS_DARK_MODE] = enabled }
    }

    suspend fun setLastLocation(lat: Double, lng: Double) {
        context.dataStore.edit { prefs ->
            prefs[LAST_KNOWN_LAT] = lat.toFloat()
            prefs[LAST_KNOWN_LNG] = lng.toFloat()
        }
    }
}
