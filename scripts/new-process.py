import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import os

# conn = engine_nexora_db.raw_connection()
# cursor = conn.cursor()
os.system("cls")

print("==========[nexora].[dbo].[StatConfig]==========")
print("\n! Please note that every input will be treated as case-sensitive")
while True:
    octo_client_name = input("\nocto client name: ")
    octo_process_name = input("octo processname name: ")
    octo_full_process_name = octo_client_name + "." + octo_process_name

    stat_table = input("statistic tablename (f: schema.table): ")
    add_cond = input("additional condition for stat: ")
    export_column = input("export column: ")
    import_column = input("import column: ")
    workitem_column = input("workitem column: ")

    while True:
        client_code = input("is the new client ms? (y/n): ")

        if client_code not in ("y", "n"):
            print("y or n")
            continue
        else:
            client_code = "ms02" if client_code == "y" else "default"
            break

    from tabulate import tabulate

    print(
        tabulate(
            [
                ["Process Name", octo_full_process_name],
                ["Table Name", stat_table],
                ["Additional Condition", add_cond],
                ["Export Column", export_column],
                ["Import Column", import_column],
                ["Workitem Column", workitem_column],
                ["Client Code", client_code],
            ],
            headers=["InputIn", "InputOut"],
        )
    )

    confirm = input("confirm (y/n): ")
    if confirm != "y":
        continue

    add_cond = "null" if add_cond in (None, "") else add_cond
    query = f"INSERT INTO StatConfig(ProcessName, TableName, ExportColumn, additionalCondition, ImportColumn, WorkitemColumn, ClientCode) VALUES({octo_full_process_name, stat_table, export_column, add_cond, import_column, workitem_column, client_code})"
    print(query)
    # try:
    #     cursor.execute(f"INSERT INTO StatConfig(ProcessName, TableName, ExportColumn, additionalCondition, ImportColumn, WorkitemColumn, ClientCode) VALUES(?,?,?,?,?,?,?)"
    #                 , (octo_full_process_name, stat_table, export_column, add_cond, import_column, workitem_column, client_code))
    #     conn.commit()
    # except Exception as e:
    #     print("Exception occured: " + e)
    #

    # cursor.close()
    # conn.close()
