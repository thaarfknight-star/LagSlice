fn main() {
    // اجرای برنامه با دسترسی ادمین لازم است: نوشتن پالیسی‌های QoS در HKLM
    // و خواندن EStats همه‌ی پروسه‌ها بدون ادمین ممکن نیست.
    #[cfg(windows)]
    {
        let manifest = r#"<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="requireAdministrator" uiAccess="false" />
      </requestedPrivileges>
    </security>
  </trustInfo>
</assembly>"#;
        let windows_attrs = tauri_build::WindowsAttributes::new().app_manifest(manifest);
        let attrs = tauri_build::Attributes::new().windows_attributes(windows_attrs);
        tauri_build::try_build(attrs).expect("failed to run tauri build");
    }
    #[cfg(not(windows))]
    tauri_build::build();
}
