use mlua::{Lua, Result};
use std::fs;

// usage: luaurun [--check] <file.luau> [more files...]
//   --check : only compile every file (syntax check), do not run
//   default : run the files in one shared Luau VM, in order
fn main() -> Result<()> {
    let mut args: Vec<String> = std::env::args().skip(1).collect();
    let check = if args.first().map(|s| s == "--check").unwrap_or(false) { args.remove(0); true } else { false };
    let lua = Lua::new();
    // __load_file(path) -> compiled chunk (used by the Roblox mock's require)
    let load = lua.create_function(|lua, path: String| {
        let src = fs::read_to_string(&path).map_err(mlua::Error::external)?;
        lua.load(&src).set_name(path.as_str()).into_function()
    })?;
    lua.globals().set("__load_file", load)?;
    let mut code = 0;
    for path in &args {
        let src = fs::read_to_string(path).expect("read");
        let chunk = lua.load(&src).set_name(path.as_str());
        let res = if check { chunk.into_function().map(|_| ()) } else { chunk.exec() };
        match res {
            Ok(_) => { if check { println!("ok  {}", path); } }
            Err(e) => { eprintln!("ERROR in {}:\n{}", path, e); code = 1; if !check { break; } }
        }
    }
    std::process::exit(code);
}
