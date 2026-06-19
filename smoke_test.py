from dotenv import load_dotenv
load_dotenv()
from e2b import Sandbox

with Sandbox.create(timeout=120) as sandbox:
    # 1. Confirm the sandbox runs a basic command
    result = sandbox.commands.run('echo "Hello from Foreman sandbox!"')
    print("STDOUT:", result.stdout)

    # 2. Clone a tiny public repo to prove git + network access work
    clone_result = sandbox.commands.run(
        'git clone https://github.com/octocat/Hello-World.git'
    )
    print("Clone exit code:", clone_result.exit_code)

    # 3. Confirm the repo actually landed on disk
    ls_result = sandbox.commands.run('ls -la')
    print(ls_result.stdout)

    # 4. Run a command inside the cloned repo
    cat_result = sandbox.commands.run('cat Hello-World/README')
    print(cat_result.stdout)

print("Sandbox closed cleanly.")