import { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId:   "com.pakupaku.app",
  appName: "PakuPaku",
  webDir:  "build",
  android: {
    backgroundColor:      "#fcf9ea",
    allowMixedContent:    false,
    captureInput:         true,
    webContentsDebuggingEnabled: false,
  },
  ios: {
    backgroundColor:      "#fcf9ea",
    contentInset:         "automatic",
    scrollEnabled:        true,
  },
  plugins: {
    CapacitorSQLite: {
      iosDatabaseLocation:   "Library/CapacitorDatabase",
      iosIsEncryption:       false,
      iosKeychainPrefix:     "pakupaku",
      androidIsEncryption:   false,
    },
  },
};

export default config;
