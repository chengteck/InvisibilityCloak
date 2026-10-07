#!/usr/bin/env python3
"""
SYNOPSIS

	InvisibilityCloak [-h, --help] [--version] [-m, --method] [-d, --directory] [-n, --name]

DESCRIPTION

	C# Tool Obfuscator

SUPPORTED OBFUSCATION METHODS

	base64 - Base64 encode all strings within project and have them decoded at runtime
	rot13 - Rotate each character in string by 13
	reverse - Reverse all strings within project and have them re-reversed at runtime
	

EXAMPLES

        ==Run InvisibilityCloak with string obfuscation==
        
	InvisibilityCloak.py -d C:\path\\to\project -n "TotallyLegitTool" -m base64
	InvisibilityCloak.py -d C:\path\\to\project -n "TotallyLegitTool" -m rot13
	InvisibilityCloak.py -d C:\path\\to\project -n "TotallyLegitTool" -m reverse


	==Run InvisibilityCloak without string obfuscation==
	
	InvisibilityCloak.py -d C:\path\\to\project -n "TotallyLegitTool"


AUTHOR

	Brett Hawkins (@h4wkst3r)

LICENSE

	Apache 2.0 License
	http://www.apache.org/licenses/LICENSE-2.0

VERSION

	0.5

"""
from sys import exit
from uuid import uuid4
from codecs import encode
from shutil import copyfile
from base64 import b64encode
from re import sub, escape, findall
from traceback import format_exc as print_traceback
from optparse import OptionParser, TitledHelpFormatter
from os import walk, path, remove, rename, getcwd, chdir


def replaceGUIDAndToolName(theDirectory: str, theName: str) -> None:
	"""
	method to generate a new project GUID (supports solutions with multiple C# projects)
	:param theDirectory: directory to find the old tool
	:param theName: name of the new tool
	:return: None
	"""
	print("\n[*] INFO: Generating new GUID(s) for C# project(s)")
	global currentToolName
	slnFile, currentToolName = "", ""
	csProjFiles = []
	assemblyInfoFiles = []

	# iterate through the project to find the VS solution file and all C# project files. also grab the paths to assembly info files
	for r, d, f in walk(theDirectory):
		for file in f:
			if file.endswith(".sln"):
				slnFile = path.join(r, file)
				currentToolName = file
			elif file.endswith(".csproj"):
				csProjFiles.append(path.join(r, file))
			elif "AssemblyInfo.cs" in file:
				assemblyInfoFiles.append(path.join(r, file))

	if not slnFile:
		print("\n[-] ERROR: No Visual Studio solution file (.sln) was found in the project directory\n")
		exit(0)

	if len(csProjFiles) == 0:
		print("\n[-] ERROR: No C# project files (.csproj) were found in the project directory\n")
		exit(0)

	# capture current tool name based on VS sln file name
	currentToolName = currentToolName.replace(".sln", "")

	print(f"[*] INFO: Found {len(csProjFiles)} C# project file(s)")
	print("[*] INFO: Changing C# project GUID(s) in below files:")
	print(slnFile)
	for csProjFile in csProjFiles:
		print(csProjFile)
	for assemblyInfoFile in assemblyInfoFiles:
		print(assemblyInfoFile)
	print("")

	# generate a new GUID for each project (keyed by project name without the .csproj extension)
	projectNameToNewGUID = {}
	for csProjFile in csProjFiles:
		projectName = path.basename(csProjFile).replace(".csproj", "")
		newGUID = str(uuid4())
		projectNameToNewGUID[projectName] = newGUID
		print(f"[*] INFO: New GUID for project '{projectName}' is {newGUID}")

	# parse the .sln once to pull each project's existing instance GUID so we can map old -> new
	# .sln project lines look like: Project("{Type-GUID}") = "ProjectName", "RelPath\ProjectName.csproj", "{Instance-GUID}"
	projectNameToOldGUID = {}
	openSLNFile = open(slnFile, 'r')
	slnLines = openSLNFile.readlines()
	openSLNFile.close()

	for line in slnLines:
		if line.lstrip().startswith("Project(") and ".csproj" in line:
			try:
				lineSplit = line.split(", ")
				projName = lineSplit[0].split("= ")[1].replace("\"", "").strip()
				instGUID = lineSplit[2].replace("\"", "").strip()
				projectNameToOldGUID[projName] = instGUID
			except (IndexError, ValueError):
				continue

	# build a map of oldGUID -> newGUID (both wrapped in braces, matching the .sln format)
	oldToNewBracedGUID = {}
	for projName, oldGUID in projectNameToOldGUID.items():
		if projName in projectNameToNewGUID:
			oldToNewBracedGUID[oldGUID] = "{" + projectNameToNewGUID[projName] + "}"

	# change the GUID(s) and tool name in the sln file
	copyfile(slnFile, slnFile + "_copy")
	openCopySLNFile = open(slnFile + "_copy", "w")

	for line in slnLines:
		# if it is the line that defines project files, replace the project's instance GUID and (only for the main project) its name
		if line.lstrip().startswith("Project(") and ".csproj" in line:
			try:
				lineSplit = line.split(", ")
				projName = lineSplit[0].split("= ")[1].replace("\"", "").strip()
				oldGUID = lineSplit[2].replace("\"", "").strip()
				if projName in projectNameToNewGUID:
					line = line.replace(oldGUID, "{" + projectNameToNewGUID[projName] + "}")
				# only rename the project that shares its name with the solution (the "main" project)
				if projName == currentToolName:
					line = line.replace(currentToolName, theName)
			except (IndexError, ValueError):
				pass
			openCopySLNFile.write(line)
		else:
			# replace any occurrences of any old project GUIDs with their matching new ones
			for oldGUID, newBracedGUID in oldToNewBracedGUID.items():
				if oldGUID in line:
					line = line.replace(oldGUID, newBracedGUID)
			openCopySLNFile.write(line)

	openCopySLNFile.close()
	remove(slnFile), rename(f"{slnFile}_copy", slnFile)

	# change the GUID and (where applicable) tool name in each C# proj file
	print("\n[*] INFO: Removing PDB string in C# project file(s)\n")
	for csProjFile in csProjFiles:
		projectName = path.basename(csProjFile).replace(".csproj", "")

		copyfile(csProjFile, f"{csProjFile}_copy")
		openCSProjFile = open(csProjFile, 'r')
		openCopyCSProjFile = open(csProjFile + "_copy", "w")
		csProjLines = openCSProjFile.readlines()

		for line in csProjLines:
			# replace every project's GUID (handles this project's own GUID and any <ProjectReference> entries to other projects in the solution)
			for otherProjName, otherNewGUID in projectNameToNewGUID.items():
				otherOldGUID = projectNameToOldGUID.get(otherProjName)
				if not otherOldGUID:
					continue
				otherCleanOldGUID = otherOldGUID.replace("{", "").replace("}", "")
				line = line.replace(otherOldGUID, "{" + otherNewGUID + "}").replace(otherCleanOldGUID, otherNewGUID)

			# replace any line in C# project file that has old tool name, except for nuget package reference or references to application icons
			# only do this inside the main project's .csproj, so cross-project references in other projects are not broken
			if projectName == currentToolName and "<PackageReference Include=" not in line and "<ApplicationIcon>" not in line:
				line = sub('(?i)' + escape(currentToolName), lambda m: theName, line)

			# remove the pdb string options from C# project file
			line = line.replace("<DebugType>pdbonly</DebugType>", "<DebugType>none</DebugType>").replace("<DebugType>full</DebugType>", "<DebugType>none</DebugType>")
			openCopyCSProjFile.write(line)

		openCSProjFile.close(), openCopyCSProjFile.close()
		remove(csProjFile), rename(f"{csProjFile}_copy", csProjFile)

	# change the info in each assemblyinfo file. match each AssemblyInfo.cs to the project it lives under
	for assemblyInfoFile in assemblyInfoFiles:
		if not path.exists(assemblyInfoFile):
			continue

		# find the .csproj whose directory is the deepest parent of this AssemblyInfo.cs
		projectName = None
		bestLen = -1
		normAssembly = assemblyInfoFile.replace("\\", "/")
		for csProjFile in csProjFiles:
			normProjDir = path.dirname(csProjFile).replace("\\", "/")
			if normAssembly.startswith(normProjDir + "/") and len(normProjDir) > bestLen:
				bestLen = len(normProjDir)
				projectName = path.basename(csProjFile).replace(".csproj", "")

		if projectName is None or projectName not in projectNameToNewGUID:
			continue

		oldGUID = projectNameToOldGUID.get(projectName, "f2ca1bb6c7e907d06dafe4687e579fce76b37e4e93b7605022da52e6ccc26fd2")
		newGUID = projectNameToNewGUID[projectName]
		tempGUID = oldGUID.replace("{", "").replace("}", "").lower()

		copyfile(assemblyInfoFile, f"{assemblyInfoFile}_copy")
		openAssemblyInfoFile = open(assemblyInfoFile, 'r')
		openCopyAssemblyInfoFile = open(f"{assemblyInfoFile}_copy", "w")

		for line in openAssemblyInfoFile.readlines():
			# only replace solution-name occurrences inside the main project's AssemblyInfo
			if projectName == currentToolName:
				line = line.replace(currentToolName, theName)
			line = line.replace(tempGUID, newGUID)
			openCopyAssemblyInfoFile.write(line)

		openAssemblyInfoFile.close(), openCopyAssemblyInfoFile.close()
		remove(assemblyInfoFile), rename(f"{assemblyInfoFile}_copy", assemblyInfoFile)

	# rename any directories or files of the current tool name with new one (only touches files tied to the main project / solution name)
	for r, d, f in walk(theDirectory):
		for file in f:
			if file == currentToolName + ".sln":
				print(f"[*] INFO: Renaming {currentToolName}.sln to {theName}.sln")
				theFile = path.join(r, file)
				newFile = theFile.replace(f"{currentToolName}.sln", f"{theName}.sln")
				rename(theFile, newFile)
			elif file == currentToolName + ".csproj":
				print(f"[*] INFO: Renaming {currentToolName}.csproj to {theName}.csproj")
				theFile = path.join(r, file)
				newFile = theFile.replace(f"{currentToolName}.csproj", f"{theName}.csproj")
				rename(theFile, newFile)
			elif currentToolName in file and file.endswith(".cs"):
				theFile = path.join(r, file)
				newFile = file.replace(currentToolName, theName)
				newFullFile = theFile.replace(file, newFile)
				print(f"[*] INFO: Renaming {theFile} to {newFullFile}")
				rename(theFile, newFullFile)

	origWorkingDir = getcwd()
	chdir(theDirectory)
	print(f"[*] INFO: Renaming directory {currentToolName} to {theName}")
	if path.exists(currentToolName):
		rename(currentToolName, theName)
	if path.isfile(currentToolName) or path.exists(theDirectory + "\\" + currentToolName):
		rename(currentToolName, theName)
	chdir(origWorkingDir)

	print(f"\n[+] SUCCESS: New GUID(s) were generated and replaced in your project(s)")
	print(f"[+] SUCCESS: New tool name of {theName} was replaced in project\n")


def reverseString(s: str) -> str:
	"""
	method to reverse a given string
	:param s: string to reversse
	:return: string reversed
	"""
	new_str = ""
	for i in s:
		new_str = i + new_str
	return new_str


def isLineMethodSignature(theLine: str) -> int:
	"""
	method to determine if line is part of a method signature (can't have dynamic strings in method singature)
	:param theLine:
	:return: 0 if not and 1 if the string contains the method signature
	"""
	if ("public" in theLine or "private" in theLine) and "string" in theLine and "=" in theLine and "(" in theLine and ")" in theLine:
		return 1
	else:
		return 0


def canProceedWithObfuscation(theLine: str, theItem: str) -> int:
	"""
	method to determine if ok to proceed with string obfuscation
	:param theLine: line of file
	:param theItem: strings of line with old tool name occurrence replaced
	:return: zero if can't obfuscate and 1 if ok
	"""
	# only obfuscate string if greater than 2 chars
	if len(theItem) <= 2:
		return 0
	# don't obfuscate string if using string interpolation
	elif ("{" in theItem or "}" in theItem and "$" in theLine) or ("String.Format(" in theLine or "string.Format(" in theLine):
		return 0
	# can't obfuscate case statements as they need to be static values
	elif theLine.strip().startswith("case") == 1:
		return 0
	# can't obfuscate const vars
	elif "const string " in theLine or "const static string" in theLine:
		return 0
	# can't obfuscate strings being compared with "is" as they must be static
	elif ("if(" in theLine or "if (" in theLine) and " is \"" in theLine:
		return 0
	# can't obfuscate strings in method signatures
	elif isLineMethodSignature(theLine) == 1:
		return 0 
	# obfuscating strings in regexes has been problematic
	elif "new Regex" in theLine or "Regex" in theLine:
		return 0
	# obfuscating unicode strings has been problematic
	elif "Encoding.Unicode.GetString" in theLine or "Encoding.Unicode.GetBytes" in theLine:
		return 0
	# obfuscating occurrence of this has been problematic
	elif "Encoding.ASCII.GetBytes" in theLine:
		return 0
	# can't obfuscate override strings
	elif "public override string" in theLine or "private override string" in theLine:
		return 0
	# don't obfuscate string that starts with or ends with '
	elif theItem.startswith("'") == 1 or theItem.endswith("'") == 1:
		return 0
	# random edge case issue with ""' in line
	elif "\"\"\'" in theLine:
		return 0
	# random edge case issue
	elif "+ @\"" in theLine or "+@\"" in theLine:
		return 0
	# random edge case issue (""" in the line)
	elif "\"\"\"" in theLine:
		return 0
	# random edge case issue ("" in the line)
	elif "\"\"" in theLine:
		return 0
	# random edge case issue (" => " in the line in switch statement)
	elif "\" => \"" in theLine or "\"=>\"" in theLine:
		return 0
	# random edge case issue (" at start of line and ending in "])). this indicates a command line switch that needs to be static
	elif theLine.strip().startswith("\"") == 1 and theLine.strip().endswith("\")]"):
		return 0
	# otherwise, it is ok to proceed with string obfuscation
	else:
		return 1


def stringObfuscate(theFile: str, theName: str, theObfMethod: str) -> None:
	"""
	method to obfuscate strings based on method entered by user
	:param theFile: filepath to obfuscate the strings
	:param theName: name of the new file
	:param theObfMethod: obfuscation method
	:return: None
	"""
	if theObfMethod == "base64":
		print(f"[*] INFO: Performing base64 obfuscation on strings in {theFile}")

	if theObfMethod == "rot13":
		print(f"[*] INFO: Performing rot13 obfuscation on strings in {theFile}")

	if theObfMethod == "reverse":
		print(f"[*] INFO: Performing reverse obfuscation on strings in {theFile}")

	# make copy of source file that modifications will be written to
	copyfile(theFile, f"{theFile}_copy")
	fIn = open(theFile, 'r')
	fInCopy = open(f"{theFile}_copy", "w")
	
	index = -1
	# get all lines in the source code file
	theLines = fIn.readlines()

	# manipulate first line of the source code file as appropriate
	if theLines[0].startswith("#define") == 1:
		theLines[0] = theLines[0].replace("using System.Text;", "").replace("using System.Linq;", "").replace("using System;", "")
		theLines[0] += "\r\nusing System.Text;\r\nusing System.Linq;\r\nusing System;\r\n"

	elif theLines[0].startswith("#define") == 0:
		theLines[0] = theLines[0].replace("using System.Text;", "").replace("using System.Linq;", "").replace("using System;", "")
		theLines[0] = f"//start\r\nusing System.Text;\r\nusing System.Linq;\r\nusing System;\r\n{theLines[0]}"

	# iterate through all of the lines in the source code file
	for line in theLines:
		index += 1
		stringsInLine, substringCount, strippedLine = "", 0, ""

		if line.strip().startswith("[") == 0:
			strippedLine = line

			if index >= 2:
				if theLines[index-2].strip().startswith("[") == 0 and theLines[index-3].strip().startswith("[") == 0:
					substringCount = strippedLine.count("\\" + "\"")
			else:
				substringCount = strippedLine.count("\\" + "\"")

			# if the line has an embedded string (\"something\"), handle it
			if substringCount >= 2 and "@" not in strippedLine and "\"" + "\\\\" + "\"" not in strippedLine and "public override string" not in strippedLine and "\\\\" + "\"\"" not in strippedLine and "String.Format(" not in strippedLine and "string.Format(" not in strippedLine:
				strippedLine = strippedLine.replace("\\" + "\"", "++====THISGETSREPLACED====++")

			# find all strings in the line and add to an array
			stringsInLine = findall(r'"([^"]*)"', strippedLine)

		# if there are strings in the line, then replace them appropriately
		if len(stringsInLine) > 0:
			# replace occurrence of old tool name with new
			strippedLine = strippedLine.replace(currentToolName, theName)

			for theItem in stringsInLine:
				# determine whether can proceed with string obfuscation
				if canProceedWithObfuscation(line, theItem):
					theString = theItem

					# if string obfuscation method is base64
					if theObfMethod == "base64":
						base64EncodedString = b64encode(theString.encode("utf-8"))
						theBase64String = str(base64EncodedString)
						theBase64String = theBase64String.replace("b'", "").replace("'", "")

						# if the line has escaped strings (e.g., \r, \t, etc.)
						if "\\r" in strippedLine or "\\n" in strippedLine or "\\t" in strippedLine or "\"" in strippedLine or "\'" in strippedLine:
							if "++====THISGETSREPLACED====++" in strippedLine:
								strippedLine = strippedLine.replace("++====THISGETSREPLACED====++", "\\" + "\"")  # remove placeholder strings
								strippedLine = strippedLine.replace("\"" + theString + "\"", "Encoding.UTF8.GetString(Convert.FromBase64String(@" + "\"" + theBase64String + "\"" + "))")
							else:
								strippedLine = strippedLine.replace("\"" + theString + "\"", "Encoding.UTF8.GetString(Convert.FromBase64String(" + "\"" + theBase64String + "\"" + "))")

							strippedLine = strippedLine.replace("@Encoding.UTF8.GetString(Convert.FromBase64String", "Encoding.UTF8.GetString(Convert.FromBase64String")
							strippedLine = strippedLine.replace("$Encoding.UTF8.GetString(Convert.FromBase64String", "Encoding.UTF8.GetString(Convert.FromBase64String")

						# if the line does not have escaped strings
						else:
							strippedLine = strippedLine.replace("++====THISGETSREPLACED====++", "\\" + "\"")  # remove placeholder strings
							strippedLine = strippedLine.replace("\"" + theString + "\"", "Encoding.UTF8.GetString(Convert.FromBase64String(@" + "\"" + theBase64String + "\"" + "))")
							strippedLine = strippedLine.replace("@Encoding.UTF8.GetString(Convert.FromBase64String", "Encoding.UTF8.GetString(Convert.FromBase64String")
							strippedLine = strippedLine.replace("$Encoding.UTF8.GetString(Convert.FromBase64String", "Encoding.UTF8.GetString(Convert.FromBase64String")

					# if string obfuscation method is rot13
					if theObfMethod == "rot13":
						rot13String = encode(theString, "rot_13")

						# if the line has escaped strings
						if "\\r" in strippedLine or "\\n" in strippedLine or "\\t" in strippedLine or "\"" in strippedLine or "\'" in strippedLine:
							if "++====THISGETSREPLACED====++" in strippedLine and "\"" not in strippedLine and "\'" not in strippedLine:
								strippedLine = strippedLine.replace("\"" + theString + "\"", "new string(@" + "\"" + rot13String + "\"" + ".Select(xAZ => (xAZ >= 'a' && xAZ <= 'z') ? (char)((xAZ - 'a' + 13) % 26 + 'a') : ((xAZ >= 'A' && xAZ <= 'Z') ? (char)((xAZ - 'A' + 13) % 26 + 'A') : xAZ)).ToArray())")
							else:
								strippedLine = strippedLine.replace("\"" + theString + "\"", "new string(" + "\"" + rot13String + "\"" + ".Select(xAZ => (xAZ >= 'a' && xAZ <= 'z') ? (char)((xAZ - 'a' + 13) % 26 + 'a') : ((xAZ >= 'A' && xAZ <= 'Z') ? (char)((xAZ - 'A' + 13) % 26 + 'A') : xAZ)).ToArray())")

							strippedLine = strippedLine.replace("\\e", "\\\\e").replace("\\g", "\\\\g").replace("\\\\\\e", "\\\\e").replace("\\\\\\g", "\\\\g").replace("\\\\\\\\e", "\\\\e").replace("\\\\\\\\g", "\\\\g")
							strippedLine = strippedLine.replace("++====THISGETSREPLACED====++", "\\" + "\"")  # remove placeholder strings
							strippedLine = strippedLine.replace("++====GUVFTRGFERCYNPRQ====++", "\\" + "\"")  # remove placeholder strings
							strippedLine = strippedLine.replace("@new string(", "new string(@").replace("$new string(", "new string(")

						# if the line does not have escaped strings
						else:
							strippedLine = strippedLine.replace("\"" + theString + "\"", "new string(@" + "\"" + rot13String + "\"" + ".Select(xAZ => (xAZ >= 'a' && x <= 'z') ? (char)((xAZ - 'a' + 13) % 26 + 'a') : ((xAZ >= 'A' && xAZ <= 'Z') ? (char)((xAZ - 'A' + 13) % 26 + 'A') : xAZ)).ToArray())")
							strippedLine = strippedLine.replace("++====THISGETSREPLACED====++", "\\" + "\"")  # remove placeholder strings
							strippedLine = strippedLine.replace("++====GUVFTRGFERCYNPRQ====++", "\\" + "\"")  # remove placeholder strings
							strippedLine = strippedLine.replace("@new string(", "new string(@").replace("$new string(", "new string(")

					# if string obfuscation method is reverse
					if theObfMethod == "reverse":
						reversedString = reverseString(theString)

						# if the line has escaped strings (e.g., \r, \t, etc.)
						if "\\r" in strippedLine or "\\n" in strippedLine or "\\t" in strippedLine or "\"" in strippedLine or "\'" in strippedLine:
							if "++====THISGETSREPLACED====++" in strippedLine:
								strippedLine = strippedLine.replace("\"" + theString + "\"", "new string(@" + "\"" + reversedString + "\"" + ".ToCharArray().Reverse().ToArray())")
							else:
								strippedLine = strippedLine.replace("\"" + theString + "\"", "new string(" + "\"" + reversedString + "\"" + ".ToCharArray().Reverse().ToArray())")

							strippedLine = strippedLine.replace("r\\", "r\\\\").replace("t\\", "t\\\\").replace("n\\", "n\\\\").replace("r\\\\\\", "r\\\\").replace("n\\\\\\", "n\\\\").replace("t\\\\\\", "t\\\\")
							strippedLine = strippedLine.replace("++====DECALPERSTEGSIHT====++", "\"\"")  # remove placeholder strings
							strippedLine = strippedLine.replace("++====THISGETSREPLACED====++", "\\" + "\"")  # remove placeholder strings
							strippedLine = strippedLine.replace("@new string(", "new string(@").replace("$new string(", "new string(")
							strippedLine = strippedLine.replace("r\\\\\\", "r\\\\").replace("n\\\\\\", "n\\\\").replace("t\\\\\\", "t\\\\")

						# if the line does not have escaped strings
						else:
							strippedLine = strippedLine.replace("\"" + theString + "\"", "new string(@" + "\"" + reversedString + "\"" + ".ToCharArray().Reverse().ToArray())")
							strippedLine = strippedLine.replace("++====DECALPERSTEGSIHT====++", "\"\"")  # remove placeholder strings
							strippedLine = strippedLine.replace("++====THISGETSREPLACED====++", "\\" + "\"")  # remove placeholder strings
							strippedLine = strippedLine.replace("@new string(", "new string(@").replace("$new string(", "new string(")

			strippedLine = strippedLine.replace("++====THISGETSREPLACED====++", "")  # remove any placeholder string that wasn't a string candidate originally
			fInCopy.write(strippedLine)

		# remove duplicate libraries for ones that are included for string deobfuscation
		elif "using System.Linq;" in line and "//start" not in line and "#define" not in line:
			line = line.replace("using System.Linq;", "")

		elif "using System.Text;" in line and "//start" not in line and "#define" not in line:
			line = line.replace("using System.Text;", "")

		elif "using System;" in line and "//start" not in line and "#define" not in line:
			line = line.replace("using System;", "")

		# replace namepace of old tool name to new tool name
		elif "namespace" in line and currentToolName in line:
			line = line.replace(currentToolName, theName)		
			fInCopy.write(line)

		# if class currently has old tool name in it, replace it
		elif f"class {currentToolName}" in line:
			line = line.replace(currentToolName, theName)
			fInCopy.write(line)

		# if line is a standard one-line comment (e.g., // something), delete it
		elif line.strip().startswith("//") and "//start\r\nusing System.Text;\r\nusing System.Linq;\r\n" not in line and "*/" not in line and "/*" not in line:
			fInCopy.write("")

		# if using library in class that has old tool name in it, replace it
		elif line.strip().startswith("using") and currentToolName in line:
			line = line.replace(currentToolName, theName)
			fInCopy.write(line)

		# replace constructor name if it has current tool name init
		elif line.strip().startswith("public" + currentToolName):
			line = line.replace(currentToolName, theName)
			fInCopy.write(line)

		# replace any occurrence of current tool name in source code
		elif currentToolName in line:
			line = line.replace(currentToolName, theName)
			fInCopy.write(line)

		# last catch for any of the placeholder strings that need removed
		elif "++====THISGETSREPLACED====++" in line:
			line = line.replace("++====THISGETSREPLACED====++", "")
			fInCopy.write(line)		

		# if no modifications need done to the line
		else:
			fInCopy.write(line)

	# close file streams and replace old source file with new modified one
	fIn.close(), fInCopy.close()
	remove(theFile), rename(f"{theFile}_copy", theFile)


def main(theObfMethod: str, theDirectory: str, theName: str) -> None:
	"""
	Manages the main procedures of Invisibility Cloak
	:param theObfMethod: obfuscation method
	:param theDirectory: directory of C# project
	:param theName: name of new tool
	:return: None
	"""
	print("""
	,                 .     .   .        ,-. .         ,   
	|         o     o |   o | o |       /    |         |   
	| ;-. . , . ,-. . |-. . | . |-  . . |    | ,-. ,-: | , 
	| | | |/  | `-. | | | | | | |   | | \    | | | | | |<  
	' ' ' '   ' `-' ' `-' ' ' ' `-' `-|  `-' ' `-' `-` ' ` 
					`-'                    
	""")

	print("====================================================")
	print(f"[*] INFO: String obfuscation method: {theObfMethod}")
	print(f"[*] INFO: Directory of C# project: {theDirectory}")
	print(f"[*] INFO: New tool name: {theName}")
	print("====================================================")

	# generate new GUID for C# project and replace tool name
	replaceGUIDAndToolName(theDirectory, theName)

	# if user wants to obfuscate strings, then proceed
	if theObfMethod != "":
		for r, d, f in walk(theDirectory):
			for file in f:
				if file.endswith(".cs") and "AssemblyInfo.cs" not in file and r.endswith("obj\\Debug") == 0 and r.endswith("obj\\Release") == 0:
					stringObfuscate(path.join(r, file), theName, theObfMethod)
	print(f'\n[+] SUCCESS: Your new tool {theName} now has the invisibility cloak applied.\n')


if __name__ == '__main__':
	try:
		parser = OptionParser(formatter=TitledHelpFormatter(), usage=globals()['__doc__'], version='0.5')
		parser.add_option('-m', '--method', dest='obfMethod', help='string obfuscation method')
		parser.add_option('-d', '--directory', dest='directory', help='directory of C# project')
		parser.add_option('-n', '--name', dest='name', help='new tool name')
		(options, args) = parser.parse_args()

		# if directory or name or not specified, display help and exit
		if options.directory is None or options.name is None:
			print("\n[-] ERROR: You must supply directory of C# project and new name for tool.\n")
			parser.print_help()
			exit(0)

		# if obfuscation method is not supported method, display help and exit
		if options.obfMethod is not None and (options.obfMethod != "base64" and options.obfMethod != "rot13" and options.obfMethod != "reverse"):
			print("\n[-] ERROR: You must supply a supported string obfuscation method\n")
			parser.print_help()
			exit(0)

		# if directory provided does not exist, display message and exit
		doesDirExist = path.isdir(options.directory)
		if doesDirExist == 0:
			print("\n[-] ERROR: Directory provided does not exist. Please check the path you are providing\n")
			exit(0)

		# initialize variables        
		theObfMethod, theDirectory, theName = options.obfMethod, options.directory, options.name

		# if no obfuscation method supplied
		if theObfMethod is None:
			theObfMethod = ""

		# proceed to main method
		main(theObfMethod, theDirectory, theName)

	except KeyboardInterrupt:  # Ctrl-C
		raise
	except SystemExit:  # sys.exit()
		raise
	except FileNotFoundError:
		raise
		print_traceback()
		exit(1)
	except Exception:
		print("\n[-] ERROR: Unexpected exception\n")
		raise
		print_traceback()
		exit(1)
